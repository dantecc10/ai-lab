#!/usr/bin/env python3
"""
AI Lab — Developer Remote Operations & System Telemetry Controller
Herramientas de control remoto, gestión de servicios, monitoreo de GPU/CPU y operaciones dev:
  - Telemetría en tiempo real (GPU VRAM, Temp, CPU %, RAM %, Swap, Disco)
  - Control de servicios systemd (gemma4, e4b, whisper, telegram, git-sentinel)
  - Inspección y control de procesos (Top CPU/RAM, matar procesos)
  - Operaciones Git rápidas para /media/darkseid/DATA/Repos
  - Ejecución remota de comandos de consola
"""

import os
import sys
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any

MANAGED_SERVICES = [
    "gemma4-server.service",
    "e4b-server.service",
    "whisper-server.service",
    "telegram-bot.service",
    "git-sentinel.service",
    "chatmanager.service",
]


class DevController:
    """Controlador de telemetría y operaciones remotas para el desarrollador."""

    @staticmethod
    def get_system_telemetry() -> str:
        """Genera un dashboard de telemetría completo de hardware y servicios."""
        lines = ["🖥️ **AI Lab — Dashboard de Telemetría del Sistema**\n"]

        # 1. GPU Telemetry (nvidia-smi)
        if shutil.which("nvidia-smi"):
            try:
                res = subprocess.run(
                    ["nvidia-smi", "--query-gpu=name,temperature.gpu,memory.used,memory.total,utilization.gpu,power.draw", "--format=csv,noheader,nounits"],
                    capture_output=True, text=True, timeout=3
                )
                if res.returncode == 0:
                    parts = [p.strip() for p in res.stdout.strip().split(",")]
                    if len(parts) >= 6:
                        name, temp, mem_used, mem_total, util, power = parts[:6]
                        mem_pct = (float(mem_used) / float(mem_total)) * 100
                        lines.append(f"🟢 **GPU ({name}):**")
                        lines.append(f"  • VRAM: `{mem_used}MB / {mem_total}MB` ({mem_pct:.1f}%)")
                        lines.append(f"  • Utilización: `{util}%` | Temp: `{temp}°C` | Potencia: `{power}W`\n")
            except Exception as e:
                lines.append(f"⚠️ Error GPU: {e}\n")

        # 2. CPU & RAM & Swap
        try:
            # Memory via free
            res_free = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=2)
            for l in res_free.stdout.strip().split("\n"):
                if l.startswith("Mem:"):
                    parts = l.split()
                    total, used, free_m = int(parts[1]), int(parts[2]), int(parts[3])
                    pct = (used / total) * 100
                    lines.append(f"🧠 **Memoria RAM:** `{used}MB / {total}MB` ({pct:.1f}%)")
                elif l.startswith("Swap:"):
                    parts = l.split()
                    s_total, s_used = int(parts[1]), int(parts[2])
                    s_pct = (s_used / s_total * 100) if s_total > 0 else 0
                    lines.append(f"💾 **Swap:** `{s_used}MB / {s_total}MB` ({s_pct:.1f}%)\n")

            # Disk usage
            st = os.statvfs("/")
            d_total = (st.f_blocks * st.f_frsize) / (1024 ** 3)
            d_free = (st.f_bavail * st.f_frsize) / (1024 ** 3)
            d_used = d_total - d_free
            lines.append(f"💿 **Disco Raíz (/):** `{d_used:.1f}GB / {d_total:.1f}GB` ({(d_used/d_total)*100:.1f}%)")

            # DATA Repos disk
            if os.path.exists("/media/darkseid/DATA"):
                st_data = os.statvfs("/media/darkseid/DATA")
                data_total = (st_data.f_blocks * st_data.f_frsize) / (1024 ** 3)
                data_free = (st_data.f_bavail * st_data.f_frsize) / (1024 ** 3)
                data_used = data_total - data_free
                lines.append(f"🗄️ **Disco DATA (/media/darkseid/DATA):** `{data_used:.1f}GB / {data_total:.1f}GB` ({(data_used/data_total)*100:.1f}%)\n")
        except Exception as e:
            lines.append(f"⚠️ Error RAM/Disco: {e}\n")

        # 3. Servicios Activos
        lines.append("⚙️ **Servicios de Inteligencia y Fondo:**")
        for svc in MANAGED_SERVICES:
            try:
                res_svc = subprocess.run(["systemctl", "--user", "is-active", svc], capture_output=True, text=True, timeout=2)
                state = res_svc.stdout.strip()
                icon = "🟢" if state == "active" else "🔴"
                clean_name = svc.replace(".service", "")
                lines.append(f"  • {icon} `{clean_name}`: *{state.upper()}*")
            except Exception:
                pass

        return "\n".join(lines)

    @staticmethod
    def manage_service(service_name: str, action: str = "status") -> str:
        """Controla un servicio systemd (start, stop, restart, status, logs)."""
        clean_name = service_name.strip()
        if not clean_name.endswith(".service") and not clean_name.endswith(".timer"):
            clean_name = f"{clean_name}.service"

        act = action.lower().strip()
        if act not in ["start", "stop", "restart", "status", "logs"]:
            return f"Acción '{act}' no válida. Opciones: start, stop, restart, status, logs."

        try:
            if act == "logs":
                res = subprocess.run(["journalctl", "--user", "-u", clean_name, "-n", "30", "--no-pager"], capture_output=True, text=True, timeout=5)
                return f"📜 **Logs de `{clean_name}`:**\n```\n{res.stdout.strip()}\n```"
            elif act == "status":
                res = subprocess.run(["systemctl", "--user", "status", clean_name, "--no-pager"], capture_output=True, text=True, timeout=5)
                return f"📋 **Estado de `{clean_name}`:**\n```\n{res.stdout.strip()}\n```"
            else:
                res = subprocess.run(["systemctl", "--user", act, clean_name], capture_output=True, text=True, timeout=10)
                if res.returncode == 0:
                    return f"✅ Servicio `{clean_name}` ejecutó `{act.upper()}` exitosamente."
                return f"⚠️ Error en `{act}` `{clean_name}`: {res.stderr.strip()}"
        except Exception as e:
            return f"Error gestionando servicio {clean_name}: {e}"

    @staticmethod
    def get_top_processes(count: int = 5) -> str:
        """Obtiene los procesos principales consumidores de CPU y Memoria."""
        try:
            # Top CPU
            res_cpu = subprocess.run(
                ["ps", "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%cpu"],
                capture_output=True, text=True, timeout=3
            )
            cpu_lines = res_cpu.stdout.strip().split("\n")[1:count+1]

            # Top RAM
            res_mem = subprocess.run(
                ["ps", "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%mem"],
                capture_output=True, text=True, timeout=3
            )
            mem_lines = res_mem.stdout.strip().split("\n")[1:count+1]

            report = ["🔥 **Procesos con Mayor Consumo:**\n", "🚀 **Top CPU:**"]
            for l in cpu_lines:
                report.append(f"  • `{l.strip()}`")

            report.append("\n🧠 **Top Memoria:**")
            for l in mem_lines:
                report.append(f"  • `{l.strip()}`")

            return "\n".join(report)
        except Exception as e:
            return f"Error obteniendo procesos: {e}"

    @staticmethod
    def git_repo_action(repo_path_or_name: str, git_command: str = "status") -> str:
        """Ejecuta una acción git en un repositorio local de /media/darkseid/DATA/Repos o ruta absoluta."""
        repos_root = Path("/media/darkseid/DATA/Repos")
        target_path = Path(repo_path_or_name)

        if not target_path.is_absolute():
            # Buscar en repos_root
            candidate = repos_root / repo_path_or_name
            if candidate.exists():
                target_path = candidate
            else:
                # Buscar en subdirectorios
                matches = list(repos_root.glob(f"**/{repo_path_or_name}"))
                if matches:
                    target_path = matches[0]
                else:
                    return f"Repositorio '{repo_path_or_name}' no encontrado en {repos_root}"

        if not (target_path / ".git").exists():
            return f"El directorio `{target_path}` no es un repositorio Git válido."

        cmd_parts = git_command.strip().split()
        allowed_cmds = ["status", "diff", "log", "branch", "pull", "fetch", "show"]
        if not cmd_parts or cmd_parts[0] not in allowed_cmds:
            return f"Comando git '{git_command}' no permitido. Permitidos: {', '.join(allowed_cmds)}"

        try:
            full_cmd = ["git", "-C", str(target_path)] + cmd_parts
            if cmd_parts[0] == "log":
                full_cmd += ["-n", "5", "--oneline"]

            res = subprocess.run(full_cmd, capture_output=True, text=True, timeout=10)
            out = res.stdout.strip() or res.stderr.strip()
            return f"📦 **Git `{git_command}` en `{target_path.name}`:**\n```\n{out}\n```"
        except Exception as e:
            return f"Error ejecutando git en {target_path}: {e}"

    @staticmethod
    def execute_shell_command(command: str) -> str:
        """Ejecuta un comando en la shell del sistema y devuelve la salida formateada."""
        # Evitar comandos destructivos sin confirmación
        blacklist = ["rm -rf /", ":(){ :|:& };:", "mkfs", "dd if="]
        for b in blacklist:
            if b in command:
                return f"⛔ Comando bloqueado por seguridad: {b}"

        try:
            res = subprocess.run(command, shell=True, capture_output=True, text=True, timeout=20)
            stdout = res.stdout.strip()
            stderr = res.stderr.strip()

            out_text = ""
            if stdout:
                out_text += f"**Salida:**\n```bash\n{stdout[:3000]}\n```"
            if stderr:
                out_text += f"\n⚠️ **Stderr:**\n```\n{stderr[:1000]}\n```"

            return out_text or "Comando ejecutado sin salida (Código 0)."
        except subprocess.TimeoutExpired:
            return "⏳ El comando excedió el tiempo límite de 20 segundos."
        except Exception as e:
            return f"Error ejecutando comando: {e}"


# Singleton
dev_controller = DevController()


if __name__ == "__main__":
    print(dev_controller.get_system_telemetry())
