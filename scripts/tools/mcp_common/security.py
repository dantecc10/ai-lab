"""Security guardrails: blocked commands, destructive patterns, SSRF, and audit logging."""

import re
from urllib.parse import urlparse
from mcp_common.audit import record_security_event

BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "dd if=", "mkfs", "chmod 777",
    "> /dev/sd", ":(){ :|:& };:", "mv / ", "rm -r /home",
    "rm -rf ~", "rm -rf /root"
]

DESTRUCTIVE_PATTERNS = ["rm ", "mv ", "chmod ", "chown ", "kill ", "pkill ", "> ", ">> "]

BLOCKED_URL_SCHEMES = ("file://", "javascript:", "data:", "ftp://")

PRIVATE_IP_RE = re.compile(
    r"^(127\.\d|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|169\.254\.|0\.|localhost)"
)


def is_blocked_command(cmd: str) -> bool:
    cmd_lower = cmd.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in cmd_lower:
            try:
                record_security_event("command_blocked", "run_command", cmd[:200])
            except Exception:
                pass
            return True
    return False


def is_destructive_command(cmd: str) -> bool:
    cmd_lower = cmd.lower().strip()
    for pattern in DESTRUCTIVE_PATTERNS:
        if pattern in cmd_lower:
            return True
    return False


def is_safe_url(url: str) -> bool:
    """Check if a URL is safe to fetch (no SSRF, no blocked schemes)."""
    try:
        if any(url.startswith(s) for s in BLOCKED_URL_SCHEMES):
            try:
                record_security_event("ssrf_blocked", "web", f"Blocked scheme: {url[:100]}")
            except Exception:
                pass
            return False
        parsed = urlparse(url)
        hostname = parsed.hostname or ""
        if PRIVATE_IP_RE.match(hostname):
            try:
                record_security_event("ssrf_blocked", "web", f"Private IP: {hostname} in {url[:100]}")
            except Exception:
                pass
            return False
        return True
    except Exception:
        return False


def sanitize_path(path: str) -> str:
    """Normalize a path and block traversal."""
    import os
    normalized = os.path.normpath(path)
    if ".." in normalized.split(os.sep):
        raise ValueError(f"Path traversal not allowed: {path}")
    return normalized
