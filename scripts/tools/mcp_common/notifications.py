"""Auto-notification system: desktop notifications after tool execution."""

import os
import subprocess
import time
import configparser
from mcp_common.paths import HOME

NOTIFY_CONFIG_PATH = os.path.join(HOME, ".config/notifications.conf")
_last_notify_time = 0


def load_notify_config() -> dict:
    """Load notification config from file."""
    config = {
        "enabled": True,
        "cooldown": 2,
        "on_error": True,
        "on_execute": True,
        "on_long_task": True,
        "long_task_seconds": 5,
        "exclude_tools": set(),
        "include_tools": set()
    }

    if os.path.exists(NOTIFY_CONFIG_PATH):
        try:
            parser = configparser.ConfigParser()
            parser.read(NOTIFY_CONFIG_PATH)

            if parser.has_section("notify"):
                config["enabled"] = parser.getboolean("notify", "enabled", fallback=True)
                config["cooldown"] = parser.getint("notify", "cooldown", fallback=2)
                config["on_error"] = parser.getboolean("notify", "on_error", fallback=True)
                config["on_execute"] = parser.getboolean("notify", "on_execute", fallback=True)
                config["on_long_task"] = parser.getboolean("notify", "on_long_task", fallback=True)
                config["long_task_seconds"] = parser.getint("notify", "long_task_seconds", fallback=5)

                exclude_str = parser.get("notify", "exclude_tools", fallback="")
                config["exclude_tools"] = set(s.strip() for s in exclude_str.split(",") if s.strip())

                include_str = parser.get("notify", "include_tools", fallback="")
                config["include_tools"] = set(s.strip() for s in include_str.split(",") if s.strip())
        except Exception:
            pass

    return config


def should_notify(tool_name: str, result: str, config: dict) -> bool:
    """Determine if we should send auto-notification."""
    global _last_notify_time

    if not config["enabled"]:
        return False

    if config["on_error"]:
        if result.startswith("Error") or "❌" in result or "⚠️" in result or "error" in result.lower()[:50]:
            return True

    now = time.time()
    if now - _last_notify_time < config["cooldown"]:
        return False

    if tool_name in config["include_tools"]:
        return True

    if tool_name in config["exclude_tools"]:
        return False

    return config["on_execute"]


def send_auto_notification(tool_name: str, arguments: dict, result: str):
    """Send automatic notification after tool execution."""
    global _last_notify_time

    icon = "dialog-information"
    if result.startswith("Error") or "❌" in result or "error" in result.lower()[:50]:
        icon = "dialog-error"
    elif "⚠️" in result or "warning" in result.lower()[:50]:
        icon = "dialog-warning"
    elif any(x in tool_name for x in ["delete", "remove", "kill", "revoke"]):
        icon = "edit-delete"
    elif any(x in tool_name for x in ["create", "save", "write", "send", "share", "commit", "push"]):
        icon = "document-new"
    elif any(x in tool_name for x in ["copy", "sync", "fetch", "download"]):
        icon = "edit-copy"
    elif "ssh" in tool_name:
        icon = "network-remote"
    elif "email" in tool_name:
        icon = "mail-send"

    msg = result[:150].replace("\n", " ").replace("\r", "")
    if len(result) > 150:
        msg += "..."

    try:
        subprocess.run(
            ["notify-send", "-u", "normal", "-i", icon, "-a", "AI Lab",
             f"🔧 {tool_name}", msg],
            capture_output=True,
            timeout=3
        )
    except Exception:
        pass

    _last_notify_time = time.time()
