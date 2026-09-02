#!/usr/bin/env python3
"""
AI Lab — Security Guard & Guardrails Interceptor
Evalúa niveles de riesgo de herramientas, bloquea patrones destructivos y
gestiona permisos human-in-the-loop antes de la ejecución.
"""

import os
import re
import json
import configparser
from pathlib import Path

DEFAULT_CONFIG_PATHS = [
    Path.home() / ".config" / "ai-lab" / "security-policies.conf",
    Path.home() / "ai-lab" / "configs" / "security-policies.conf",
    Path(__file__).resolve().parent.parent.parent / "configs" / "security-policies.conf"
]

DEFAULT_BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/(?:$|\s|\*)",
    r":\(\){\s*:\|:&\s*};:",
    r"mkfs\.",
    r"dd\s+if=.*of=/dev/(?:sd[a-z]|nvme[0-9]n[0-9]|dm-[0-9])",
    r">\s*/dev/sd[a-z]",
    r">\s*/dev/nvme",
    r"chmod\s+-R\s+777\s+/(?:$|\s)",
    r"rm\s+-rf\s+/boot",
    r"rm\s+-rf\s+/etc"
]

class SecurityGuard:
    """Validador de políticas de seguridad y guardrails de ejecución."""

    def __init__(self, config_path: str | Path | None = None):
        self.config_path = self._find_config(config_path)
        self.security_mode = "standard"
        self.require_confirmation_high_risk = True
        self.block_dangerous_patterns = True
        self.safe_tools: set[str] = set()
        self.medium_tools: set[str] = set()
        self.high_risk_tools: set[str] = set()
        self.blocked_patterns: list[re.Pattern] = []

        self._load_config()

    def _find_config(self, explicit_path: str | Path | None) -> Path | None:
        if explicit_path and Path(explicit_path).exists():
            return Path(explicit_path)
        for p in DEFAULT_CONFIG_PATHS:
            if p.exists():
                return p
        return None

    def _load_config(self):
        """Carga y parsea la configuración de políticas."""
        if not self.config_path:
            self._apply_fallback_policies()
            return

        parser = configparser.ConfigParser()
        try:
            parser.read(str(self.config_path), encoding="utf-8")
            
            # General
            if parser.has_section("general"):
                self.security_mode = parser.get("general", "security_mode", fallback="standard").strip().lower()
                self.require_confirmation_high_risk = parser.getboolean("general", "require_confirmation_high_risk", fallback=True)
                self.block_dangerous_patterns = parser.getboolean("general", "block_dangerous_patterns", fallback=True)

            # Risk levels
            if parser.has_section("risk_levels"):
                for level, target_set in [("safe", self.safe_tools), ("medium", self.medium_tools), ("high_risk", self.high_risk_tools)]:
                    raw_val = parser.get("risk_levels", level, fallback="[]")
                    try:
                        parsed = json.loads(raw_val)
                        if isinstance(parsed, list):
                            target_set.update(parsed)
                    except json.JSONDecodeError:
                        pass

            # Dangerous patterns
            patterns = []
            if parser.has_section("dangerous_command_patterns"):
                raw_patterns = parser.get("dangerous_command_patterns", "patterns", fallback="[]")
                try:
                    patterns = json.loads(raw_patterns)
                except json.JSONDecodeError:
                    pass

            if not patterns:
                patterns = DEFAULT_BLOCKED_PATTERNS

            self.blocked_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]

        except Exception as e:
            self._apply_fallback_policies()

    def _apply_fallback_policies(self):
        """Aplica políticas predeterminadas de resguardo si no hay archivo de configuración."""
        self.safe_tools = {
            "list_directory", "file_info", "search_files", "read_file", "get_system_info",
            "get_gpu_status", "web_search", "open_url", "media_control", "spotify_search",
            "spotify_now", "weather", "timer", "notes", "memory_search", "memory_context",
            "memory_list", "network_ping", "network_info", "process_list", "cron_list",
            "monitor_realtime", "disk_usage", "gh_repos_list", "git_status", "git_log",
            "git_diff", "docker_ps", "media_view", "r2_list", "r2_status", "browse_web",
            "audit_get_metrics", "audit_list_traces"
        }
        self.medium_tools = {
            "write_file", "send_notification", "notify_contextual", "spotify_play",
            "spotify_pause", "clipboard", "brightness", "memory_save", "memory_delete",
            "file_compress", "file_extract", "git_commit", "chat_export", "chat_share",
            "r2_upload", "r2_delete", "kasa_set_plug_state"
        }
        self.high_risk_tools = {
            "run_command", "run_python_script", "system_shutdown", "process_kill",
            "cron_add", "cron_delete", "git_push", "git_pull", "file_permissions",
            "email_send", "ssh_connect", "ssh_copy", "ssh_sync"
        }
        self.blocked_patterns = [re.compile(p, re.IGNORECASE) for p in DEFAULT_BLOCKED_PATTERNS]

    def get_risk_level(self, tool_name: str) -> str:
        """Devuelve el nivel de riesgo de una herramienta: 'safe', 'medium', 'high_risk' o 'unknown'."""
        if tool_name in self.safe_tools:
            return "safe"
        if tool_name in self.medium_tools:
            return "medium"
        if tool_name in self.high_risk_tools:
            return "high_risk"
        return "medium" if self.security_mode == "permissive" else "high_risk"

    def scan_command_for_threats(self, command: str) -> tuple[bool, str]:
        """Escanea un comando de shell en busca de patrones destructivos bloqueados."""
        if not self.block_dangerous_patterns or not command:
            return False, ""

        for pattern in self.blocked_patterns:
            if pattern.search(command):
                return True, f"Comando bloqueado por política de seguridad: patrón destructivo detectado '{pattern.pattern}'"
        return False, ""

    def evaluate_execution(
        self,
        tool_name: str,
        arguments: dict,
        user_confirmed: bool = False
    ) -> dict:
        """
        Evalúa si la ejecución de una herramienta está permitida.
        Retorna un dict con {allowed: bool, risk: str, requires_confirmation: bool, reason: str, warning: str}.
        """
        risk = self.get_risk_level(tool_name)

        # 1. Escaneo específico de comandos de shell
        if tool_name == "run_command":
            cmd = arguments.get("command", "")
            is_threat, reason = self.scan_command_for_threats(cmd)
            if is_threat:
                return {
                    "allowed": False,
                    "risk": "blocked",
                    "requires_confirmation": False,
                    "reason": reason,
                    "warning": f"CRITICAL: {reason}"
                }

        # 2. Modo estricto o herramientas de alto riesgo
        if risk == "high_risk" and self.require_confirmation_high_risk:
            if not user_confirmed and self.security_mode != "permissive":
                return {
                    "allowed": False,
                    "risk": risk,
                    "requires_confirmation": True,
                    "reason": f"La herramienta '{tool_name}' está clasificada como de alto riesgo y requiere confirmación interactiva.",
                    "warning": f"Acción de alto impacto detectada ({tool_name})."
                }

        return {
            "allowed": True,
            "risk": risk,
            "requires_confirmation": False,
            "reason": "Ejecución autorizada bajo la política activa.",
            "warning": ""
        }

if __name__ == "__main__":
    guard = SecurityGuard()
    print(f"[+] SecurityGuard iniciado en modo: {guard.security_mode}")
    print(f"[+] Safe tools: {len(guard.safe_tools)} | Medium: {len(guard.medium_tools)} | High risk: {len(guard.high_risk_tools)}")
    
    # Test safe
    res_safe = guard.evaluate_execution("get_system_info", {})
    print(f"Test get_system_info -> allowed={res_safe['allowed']}, risk={res_safe['risk']}")
    
    # Test blocked
    res_blocked = guard.evaluate_execution("run_command", {"command": "rm -rf / --no-preserve-root"})
    print(f"Test rm -rf / -> allowed={res_blocked['allowed']}, reason={res_blocked['reason']}")
    
    # Test high risk
    res_high = guard.evaluate_execution("system_shutdown", {"action": "reboot"})
    print(f"Test system_shutdown -> allowed={res_high['allowed']}, requires_confirmation={res_high['requires_confirmation']}")
