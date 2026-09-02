"""Audit & monitoring tools — query tool usage, security events, and system errors."""

import json
from mcp_common.audit import (
    get_metrics, list_recent, list_security_events,
    list_errors, rotate_old_records,
)

TOOLS = [
    {
        "name": "audit_metrics",
        "description": "Métricas agregadas de uso de herramientas: total llamadas, success rate, top tools, latencia promedio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours": {"type": "integer", "description": "Horas hacia atrás (default 24).", "default": 24}
            }
        }
    },
    {
        "name": "audit_recent",
        "description": "Últimas llamadas a herramientas con detalles: args, resultado, duración, severidad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Número de registros (default 20).", "default": 20},
                "tool_filter": {"type": "string", "description": "Filtrar por nombre de tool."},
                "errors_only": {"type": "boolean", "description": "Solo mostrar errores.", "default": False}
            }
        }
    },
    {
        "name": "audit_search",
        "description": "Búsqueda de llamadas por tool, severidad, o estado de éxito.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "Nombre de la tool a buscar."},
                "severity": {"type": "string", "description": "Filtrar por severidad: INFO, WARN, ERROR, CRITICAL."},
                "errors_only": {"type": "boolean", "description": "Solo errores.", "default": False},
                "limit": {"type": "integer", "description": "Número de resultados (default 20).", "default": 20}
            }
        }
    },
    {
        "name": "audit_security",
        "description": "Eventos de seguridad recientes: SSRF bloqueado, comandos bloqueados, path traversal.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Número de eventos (default 20).", "default": 20}
            }
        }
    },
    {
        "name": "audit_errors",
        "description": "Errores del sistema: crashes, import errors, runtime exceptions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Número de errores (default 20).", "default": 20},
                "module": {"type": "string", "description": "Filtrar por módulo (parcial)."}
            }
        }
    },
    {
        "name": "audit_tool_timeline",
        "description": "Timeline de uso de una tool específica: cuántas veces se llamó por hora.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "Nombre de la tool.", "default": ""},
                "hours": {"type": "integer", "description": "Horas hacia atrás (default 24).", "default": 24}
            },
            "required": ["tool"]
        }
    },
    {
        "name": "audit_rotate",
        "description": "Limpiar registros antiguos de la base de datos de auditoría.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "days": {"type": "integer", "description": "Días de retención (default 90).", "default": 90}
            }
        }
    },
]


def _audit_metrics_handler(hours: int = 24) -> str:
    try:
        data = get_metrics(hours)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"


def _audit_recent_handler(limit: int = 20, tool_filter: str = "", errors_only: bool = False) -> str:
    try:
        data = list_recent(limit, tool_filter, errors_only)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"


def _audit_search_handler(tool: str = "", severity: str = "", errors_only: bool = False, limit: int = 20) -> str:
    try:
        data = list_recent(limit, tool, errors_only)
        if severity:
            data = [r for r in data if r.get("severity", "").upper() == severity.upper()]
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"


def _audit_security_handler(limit: int = 20) -> str:
    try:
        data = list_security_events(limit)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"


def _audit_errors_handler(limit: int = 20, module: str = "") -> str:
    try:
        data = list_errors(limit, module)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"


def _audit_tool_timeline_handler(tool: str, hours: int = 24) -> str:
    try:
        data = get_metrics(hours)
        hourly = data.get("hourly", [])
        return json.dumps({"tool": tool, "period_hours": hours, "hourly_calls": hourly}, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error: {e}"


def _audit_rotate_handler(days: int = 90) -> str:
    try:
        rotate_old_records(days)
        return json.dumps({"status": "ok", "rotated_older_than_days": days})
    except Exception as e:
        return f"Error: {e}"


HANDLERS = {
    "audit_metrics": _audit_metrics_handler,
    "audit_recent": _audit_recent_handler,
    "audit_search": _audit_search_handler,
    "audit_security": _audit_security_handler,
    "audit_errors": _audit_errors_handler,
    "audit_tool_timeline": _audit_tool_timeline_handler,
    "audit_rotate": _audit_rotate_handler,
}
