"""Unified audit engine — SQLite with WAL mode, connection pooling, and rotation."""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "ai-lab" / "audit.db"

_local = threading.local()


def _get_conn(db_path: Path) -> sqlite3.Connection:
    """Thread-local connection pooling."""
    if not hasattr(_local, "connections"):
        _local.connections = {}
    key = str(db_path)
    if key not in _local.connections:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=3000")
        conn.row_factory = sqlite3.Row
        _local.connections[key] = conn
    return _local.connections[key]


def init_audit_db(db_path: Path = DEFAULT_DB_PATH):
    """Create tables and indexes if they don't exist."""
    conn = _get_conn(db_path)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS tool_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            session_id TEXT,
            tool_name TEXT NOT NULL,
            arguments_json TEXT,
            result_preview TEXT,
            result_size INTEGER,
            duration_ms REAL,
            success INTEGER NOT NULL,
            error_message TEXT,
            severity TEXT DEFAULT 'INFO',
            source TEXT DEFAULT 'mcp',
            gpu_vram_mb REAL,
            gpu_temp_c REAL
        );

        CREATE TABLE IF NOT EXISTS security_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            event_type TEXT NOT NULL,
            tool_name TEXT,
            details TEXT,
            source_ip TEXT
        );

        CREATE TABLE IF NOT EXISTS system_errors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT DEFAULT (datetime('now')),
            module TEXT,
            error_type TEXT,
            message TEXT,
            traceback TEXT
        );

        CREATE INDEX IF NOT EXISTS idx_tc_timestamp ON tool_calls(timestamp);
        CREATE INDEX IF NOT EXISTS idx_tc_tool ON tool_calls(tool_name);
        CREATE INDEX IF NOT EXISTS idx_tc_success ON tool_calls(success);
        CREATE INDEX IF NOT EXISTS idx_tc_severity ON tool_calls(severity);
        CREATE INDEX IF NOT EXISTS idx_se_timestamp ON security_events(timestamp);
        CREATE INDEX IF NOT EXISTS idx_se_type ON security_events(event_type);
        CREATE INDEX IF NOT EXISTS idx_se_timestamp ON system_errors(timestamp);
    """)
    conn.commit()


def record_tool_call(
    tool_name: str,
    arguments: dict,
    result: str = "",
    duration_ms: float = 0.0,
    success: bool = True,
    error_message: str = "",
    severity: str = "INFO",
    source: str = "mcp",
    session_id: str = "",
    db_path: Path = DEFAULT_DB_PATH,
):
    """Record a tool execution in the audit database."""
    args_json = json.dumps(arguments, ensure_ascii=False) if isinstance(arguments, dict) else str(arguments)
    result_preview = result[:500] if result else ""
    result_size = len(result) if result else 0

    conn = _get_conn(db_path)
    conn.execute("""
        INSERT INTO tool_calls (
            session_id, tool_name, arguments_json, result_preview, result_size,
            duration_ms, success, error_message, severity, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        session_id, tool_name, args_json, result_preview, result_size,
        round(duration_ms, 2), 1 if success else 0, error_message, severity, source
    ))
    conn.commit()


def record_security_event(
    event_type: str,
    tool_name: str = "",
    details: str = "",
    source_ip: str = "",
    db_path: Path = DEFAULT_DB_PATH,
):
    """Record a security event (SSRF blocked, command blocked, etc.)."""
    conn = _get_conn(db_path)
    conn.execute("""
        INSERT INTO security_events (event_type, tool_name, details, source_ip)
        VALUES (?, ?, ?, ?)
    """, (event_type, tool_name, details, source_ip))
    conn.commit()


def record_system_error(
    module: str,
    error_type: str,
    message: str,
    tb: str = "",
    db_path: Path = DEFAULT_DB_PATH,
):
    """Record a system error (import error, runtime crash, etc.)."""
    conn = _get_conn(db_path)
    conn.execute("""
        INSERT INTO system_errors (module, error_type, message, traceback)
        VALUES (?, ?, ?, ?)
    """, (module, error_type, message, tb))
    conn.commit()


def get_metrics(hours: int = 24, db_path: Path = DEFAULT_DB_PATH) -> dict:
    """Aggregated metrics for the last N hours."""
    conn = _get_conn(db_path)
    row = conn.execute("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as ok,
            ROUND(AVG(duration_ms), 2) as avg_ms,
            ROUND(MAX(duration_ms), 2) as max_ms
        FROM tool_calls
        WHERE timestamp >= datetime('now', ?)
    """, (f"-{hours} hours",)).fetchone()

    total = row["total"] or 0
    ok = row["ok"] or 0

    top = conn.execute("""
        SELECT tool_name, COUNT(*) as cnt, ROUND(AVG(duration_ms), 2) as avg_ms,
               SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as errors
        FROM tool_calls
        WHERE timestamp >= datetime('now', ?)
        GROUP BY tool_name ORDER BY cnt DESC LIMIT 10
    """, (f"-{hours} hours",)).fetchall()

    hourly = conn.execute("""
        SELECT strftime('%H', timestamp) as hour, COUNT(*) as cnt
        FROM tool_calls
        WHERE timestamp >= datetime('now', ?)
        GROUP BY hour ORDER BY hour
    """, (f"-{hours} hours",)).fetchall()

    return {
        "period_hours": hours,
        "total_calls": total,
        "success_rate_pct": round(ok / total * 100, 2) if total else 100.0,
        "avg_duration_ms": row["avg_ms"] or 0,
        "max_duration_ms": row["max_ms"] or 0,
        "top_tools": [{"tool": r["tool_name"], "calls": r["cnt"], "avg_ms": r["avg_ms"], "errors": r["errors"]} for r in top],
        "hourly": [{"hour": r["hour"], "calls": r["cnt"]} for r in hourly],
    }


def list_recent(
    limit: int = 20,
    tool_filter: str = "",
    errors_only: bool = False,
    db_path: Path = DEFAULT_DB_PATH,
) -> list[dict]:
    """Recent tool calls with optional filters."""
    conn = _get_conn(db_path)
    query = "SELECT id, timestamp, tool_name, arguments_json, result_preview, duration_ms, success, error_message, severity FROM tool_calls"
    conditions = []
    params = []

    if tool_filter:
        conditions.append("tool_name = ?")
        params.append(tool_filter)
    if errors_only:
        conditions.append("success = 0")

    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [
        {
            "id": r["id"], "timestamp": r["timestamp"], "tool": r["tool_name"],
            "args": r["arguments_json"], "result": r["result_preview"],
            "duration_ms": r["duration_ms"], "success": bool(r["success"]),
            "error": r["error_message"], "severity": r["severity"],
        }
        for r in rows
    ]


def list_security_events(limit: int = 20, db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Recent security events."""
    conn = _get_conn(db_path)
    rows = conn.execute("""
        SELECT id, timestamp, event_type, tool_name, details, source_ip
        FROM security_events ORDER BY id DESC LIMIT ?
    """, (limit,)).fetchall()
    return [
        {"id": r["id"], "timestamp": r["timestamp"], "type": r["event_type"],
         "tool": r["tool_name"], "details": r["details"], "ip": r["source_ip"]}
        for r in rows
    ]


def list_errors(limit: int = 20, module_filter: str = "", db_path: Path = DEFAULT_DB_PATH) -> list[dict]:
    """Recent system errors."""
    conn = _get_conn(db_path)
    query = "SELECT id, timestamp, module, error_type, message, traceback FROM system_errors"
    params = []
    if module_filter:
        query += " WHERE module LIKE ?"
        params.append(f"%{module_filter}%")
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [
        {"id": r["id"], "timestamp": r["timestamp"], "module": r["module"],
         "type": r["error_type"], "message": r["message"], "traceback": r["traceback"]}
        for r in rows
    ]


def rotate_old_records(days: int = 90, db_path: Path = DEFAULT_DB_PATH):
    """Delete records older than N days and vacuum."""
    conn = _get_conn(db_path)
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    for table in ("tool_calls", "security_events", "system_errors"):
        conn.execute(f"DELETE FROM {table} WHERE timestamp < ?", (cutoff,))
    conn.execute("VACUUM")
    conn.commit()
