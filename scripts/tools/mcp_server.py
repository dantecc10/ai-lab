#!/usr/bin/env python3
"""
MCP Server orchestrator — loads domain modules, dispatches JSON-RPC over stdio.
Drop-in replacement for system_mcp_server.py (same protocol, same tools).
"""

import sys
import json
import time
import inspect

from mcp_domain import load_all_domains
from mcp_common.keyboard import flash_keyboard_status
from mcp_common.logging import log_operation
from mcp_common.audit import init_audit_db, record_tool_call, record_security_event, record_system_error
from mcp_common.notifications import load_notify_config, should_notify, send_auto_notification


def _call_handler(handler, arguments):
    """Call handler with correct signature: named params or args dict."""
    sig = inspect.signature(handler)
    params = list(sig.parameters.keys())
    if len(params) == 1 and params[0] == 'args':
        return handler(arguments)
    return handler(**arguments)

# Load all domain tools at startup
ALL_TOOLS, ALL_HANDLERS = load_all_domains()

# Initialize audit database at startup
init_audit_db()

# Notification config at module level (fixes scoping bug)
_notify_config = load_notify_config()


def handle_request(request: dict) -> dict:
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "system-mcp-server",
                    "version": "2.1.0"
                }
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": ALL_TOOLS}
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        flash_keyboard_status(tool_name)

        if tool_name not in ALL_HANDLERS:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
            }

        # Security guardrail — inline blocked commands
        try:
            from mcp_common.security import is_blocked_command
            if tool_name == "run_command":
                cmd = arguments.get("command", "")
                if is_blocked_command(cmd):
                    record_tool_call(tool_name, arguments, f"Blocked: {cmd}", 0.0, False, "Blocked dangerous command", "WARN", "security_guard")
                    return {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "result": {
                            "content": [{"type": "text", "text": f"Blocked: dangerous command pattern detected: {cmd}"}],
                            "isError": True
                        }
                    }
        except Exception as e:
            record_system_error("mcp_server", "SecurityGuardError", str(e))

        # External security guard (if available)
        try:
            from scripts.tools.security_guard import SecurityGuard
            guard = SecurityGuard()
            eval_res = guard.evaluate_execution(tool_name, arguments, user_confirmed=arguments.get("confirm", False))
            if not eval_res["allowed"]:
                err_msg = eval_res["reason"]
                record_tool_call(tool_name, arguments, err_msg, 0.0, False, err_msg, "WARN", "security_guard")
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": f"Blocked by security policy: {err_msg}"}],
                        "isError": True
                    }
                }
        except Exception:
            pass

        t_start = time.time()
        try:
            result = _call_handler(ALL_HANDLERS[tool_name], arguments)
        except Exception as e:
            result = f"Error: {e}"
            record_system_error(f"mcp_domain.{tool_name}", type(e).__name__, str(e))
        duration_ms = (time.time() - t_start) * 1000.0

        # Audit trace via unified audit engine
        success = not (isinstance(result, str) and result.startswith("Error"))
        error_msg = result if not success else ""
        severity = "ERROR" if not success else "INFO"
        record_tool_call(tool_name, arguments, str(result)[:500], duration_ms, success, error_msg, severity, "mcp")

        # Auto-notification
        try:
            if should_notify(tool_name, result, _notify_config):
                send_auto_notification(tool_name, arguments, result)
        except Exception:
            pass

        # Format response
        if isinstance(result, dict):
            return {"jsonrpc": "2.0", "id": req_id, "result": result}
        elif isinstance(result, str):
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": result}]}
            }
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {"content": [{"type": "text", "text": str(result)}]}
            }

    elif method == "notifications/initialized":
        return None
    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


if __name__ == "__main__":
    # Rotate old records on startup (90 days)
    try:
        from mcp_common.audit import rotate_old_records
        rotate_old_records(90)
    except Exception:
        pass

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
