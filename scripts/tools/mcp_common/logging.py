"""Operation logging — delegates to audit.py SQLite engine, keeps flat file backup."""

import json
import os
from datetime import datetime
from mcp_common.paths import HOME
from mcp_common.audit import record_tool_call

LOG_FILE = os.path.join(HOME, ".config/system-tools.log")


def log_operation(tool: str, args: dict, result: str):
    """Log to both SQLite audit database and flat file backup."""
    try:
        success = not (isinstance(result, str) and result.startswith("Error"))
        record_tool_call(
            tool_name=tool,
            arguments=args if isinstance(args, dict) else {"raw": str(args)},
            result=str(result)[:500],
            success=success,
            source="handler",
        )
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {tool}({json.dumps(args, ensure_ascii=False)}) -> {str(result)[:200]}\n")
    except Exception:
        pass
