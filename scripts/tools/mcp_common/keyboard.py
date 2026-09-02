"""Visual keyboard feedback: flash ASUS keyboard LEDs per tool category."""

import threading


def flash_keyboard_status(tool_name: str):
    """Dispatch automatic LED feedback on the ASUS keyboard based on the invoked tool."""
    def _run():
        try:
            from visual_notifier import notifier
            t = (tool_name or "").lower()
            if any(k in t for k in ["memory", "note", "reminder"]):
                notifier.animate(colors=["bf00ff", "7f00ff", "00ffff"], duration=0.7, speed_ms=110)
            elif any(k in t for k in ["append", "write", "replace", "file", "git"]):
                notifier.animate(colors=["00ff66", "00e5ff", "00ffff"], duration=0.7, speed_ms=110)
            elif any(k in t for k in ["command", "bash", "python", "script", "gpu", "system"]):
                notifier.animate(colors=["ffaa00", "ffd700", "00ffff"], duration=0.7, speed_ms=110)
            elif "alert" in t or "visual" in t:
                pass
            else:
                notifier.animate(colors=["0088ff", "00ffff"], duration=0.5, speed_ms=90)
        except Exception:
            pass
    threading.Thread(target=_run, daemon=True).start()
