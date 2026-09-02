"""Audit dashboard — API endpoints and HTML dashboard for tool usage monitoring."""

import sys
import os
import json
from pathlib import Path
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse

# Add scripts/tools to path for audit imports
sys.path.insert(0, str(Path.home() / "ai-lab" / "scripts" / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "scripts" / "tools"))

from mcp_common.audit import (
    init_audit_db, get_metrics, list_recent,
    list_security_events, list_errors, DEFAULT_DB_PATH,
)

router = APIRouter(prefix="/audit", tags=["audit"])

# Initialize on import
init_audit_db()


@router.get("", response_class=HTMLResponse)
async def dashboard():
    """Serve the audit dashboard HTML."""
    html_path = Path(__file__).parent.parent.parent / "templates" / "audit.html"
    if html_path.exists():
        return HTMLResponse(content=html_path.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Audit Dashboard</h1><p>Template not found.</p>", status_code=404)


@router.get("/api/metrics")
async def api_metrics(hours: int = 24):
    """Aggregated metrics JSON."""
    return JSONResponse(content=get_metrics(hours))


@router.get("/api/recent")
async def api_recent(limit: int = 20, tool: str = "", errors: bool = False):
    """Recent tool calls JSON."""
    return JSONResponse(content=list_recent(limit, tool, errors))


@router.get("/api/security")
async def api_security(limit: int = 20):
    """Security events JSON."""
    return JSONResponse(content=list_security_events(limit))


@router.get("/api/errors")
async def api_errors(limit: int = 20, module: str = ""):
    """System errors JSON."""
    return JSONResponse(content=list_errors(limit, module))


@router.get("/api/timeline")
async def api_timeline(hours: int = 24):
    """Hourly call timeline for charts."""
    data = get_metrics(hours)
    return JSONResponse(content={"hourly": data.get("hourly", []), "top_tools": data.get("top_tools", [])})
