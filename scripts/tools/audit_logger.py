#!/usr/bin/env python3
"""
AI Lab — Audit Logger & Local Tracing Engine
Registra trazas de ejecución de herramientas, latencia, consumo estimado de tokens,
salud de GPU y métricas de rendimiento en SQLite local.
"""

import os
import sys
import json
import time
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

DEFAULT_DB_PATH = Path.home() / ".local" / "share" / "ai-lab" / "audit_traces.db"

class AuditLogger:
    """Motor de trazabilidad y métricas de ejecución para AI Lab."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        """Inicializa las tablas de auditoría."""
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_traces (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                session_id TEXT,
                tool_name TEXT NOT NULL,
                arguments_json TEXT,
                duration_ms REAL,
                success INTEGER NOT NULL,
                error_message TEXT,
                tokens_estimate INTEGER DEFAULT 0,
                gpu_vram_used_mb REAL DEFAULT 0,
                gpu_temp_c REAL DEFAULT 0
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON audit_traces(timestamp);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_tool ON audit_traces(tool_name);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_audit_success ON audit_traces(success);")
            conn.commit()

    def _get_gpu_snapshot(self) -> tuple[float, float]:
        """Obtiene una muestra rápida de VRAM usada (MB) y Temperatura (°C) de la GPU."""
        try:
            cmd = ["nvidia-smi", "--query-gpu=memory.used,temperature.gpu", "--format=csv,noheader,nounits"]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=1.0)
            if res.returncode == 0:
                parts = res.stdout.strip().split(",")
                if len(parts) >= 2:
                    return float(parts[0].strip()), float(parts[1].strip())
        except Exception:
            pass
        return 0.0, 0.0

    def record_trace(
        self,
        tool_name: str,
        arguments: dict | str,
        duration_ms: float,
        success: bool,
        error_message: str = "",
        session_id: str = "",
        tokens_estimate: int = 0
    ) -> int:
        """Registra una ejecución de herramienta en la base de datos de auditoría."""
        if isinstance(arguments, dict):
            args_str = json.dumps(arguments, ensure_ascii=False)
        else:
            args_str = str(arguments)

        vram_mb, temp_c = self._get_gpu_snapshot()

        # Si no se pasó tokens_estimate, estimar por tamaño de argumentos + error
        if tokens_estimate <= 0:
            tokens_estimate = max(1, len(args_str) // 4 + len(error_message) // 4)

        with self._get_connection() as conn:
            cursor = conn.execute("""
            INSERT INTO audit_traces (
                session_id, tool_name, arguments_json, duration_ms,
                success, error_message, tokens_estimate,
                gpu_vram_used_mb, gpu_temp_c
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                session_id, tool_name, args_str, round(duration_ms, 2),
                1 if success else 0, error_message, tokens_estimate,
                vram_mb, temp_c
            ))
            conn.commit()
            return cursor.lastrowid

    def get_metrics(self, hours: int = 24) -> dict:
        """Calcula métricas agregadas de rendimiento de las últimas N horas."""
        with self._get_connection() as conn:
            # Resumen global
            row = conn.execute("""
            SELECT 
                COUNT(*) as total_calls,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_calls,
                AVG(duration_ms) as avg_duration_ms,
                MAX(duration_ms) as max_duration_ms,
                SUM(tokens_estimate) as total_tokens,
                AVG(gpu_vram_used_mb) as avg_vram_mb,
                MAX(gpu_temp_c) as max_temp_c
            FROM audit_traces
            WHERE timestamp >= datetime('now', ?)
            """, (f"-{hours} hours",)).fetchone()

            total = row["total_calls"] or 0
            success_count = row["successful_calls"] or 0
            success_rate = (success_count / total * 100.0) if total > 0 else 100.0

            # Top herramientas
            top_rows = conn.execute("""
            SELECT tool_name, COUNT(*) as count, AVG(duration_ms) as avg_ms, SUM(CASE WHEN success=0 THEN 1 ELSE 0 END) as errors
            FROM audit_traces
            WHERE timestamp >= datetime('now', ?)
            GROUP BY tool_name
            ORDER BY count DESC
            LIMIT 10
            """, (f"-{hours} hours",)).fetchall()

            top_tools = [
                {"tool": r["tool_name"], "calls": r["count"], "avg_duration_ms": round(r["avg_ms"] or 0, 2), "errors": r["errors"]}
                for r in top_rows
            ]

            # Errores recientes
            error_rows = conn.execute("""
            SELECT timestamp, tool_name, error_message
            FROM audit_traces
            WHERE success = 0 AND timestamp >= datetime('now', ?)
            ORDER BY timestamp DESC
            LIMIT 5
            """, (f"-{hours} hours",)).fetchall()

            recent_errors = [
                {"timestamp": r["timestamp"], "tool": r["tool_name"], "error": r["error_message"]}
                for r in error_rows
            ]

            return {
                "period_hours": hours,
                "total_calls": total,
                "success_rate_pct": round(success_rate, 2),
                "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
                "max_duration_ms": round(row["max_duration_ms"] or 0, 2),
                "total_tokens_estimate": row["total_tokens"] or 0,
                "avg_gpu_vram_mb": round(row["avg_vram_mb"] or 0, 2),
                "max_gpu_temp_c": round(row["max_temp_c"] or 0, 2),
                "top_tools": top_tools,
                "recent_errors": recent_errors
            }

    def list_recent_traces(self, limit: int = 15, errors_only: bool = False) -> list[dict]:
        """Recupera la lista de trazas recientes."""
        query = "SELECT id, timestamp, tool_name, duration_ms, success, error_message, gpu_vram_used_mb FROM audit_traces"
        params = []
        if errors_only:
            query += " WHERE success = 0"
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()
            return [
                {
                    "id": r["id"],
                    "timestamp": r["timestamp"],
                    "tool": r["tool_name"],
                    "duration_ms": r["duration_ms"],
                    "success": bool(r["success"]),
                    "error": r["error_message"],
                    "vram_mb": r["gpu_vram_used_mb"]
                }
                for r in rows
            ]

if __name__ == "__main__":
    logger = AuditLogger()
    print(f"[+] AuditLogger conectado en: {logger.db_path}")
    
    # Registro de prueba
    t0 = time.time()
    time.sleep(0.01)
    dur = (time.time() - t0) * 1000
    trace_id = logger.record_trace("get_system_info", {"format": "json"}, dur, True, "", "session_test")
    print(f"[+] Trace registrado con ID: {trace_id}")
    
    metrics = logger.get_metrics(24)
    print(f"[+] Métricas 24h: {json.dumps(metrics, indent=2)}")
