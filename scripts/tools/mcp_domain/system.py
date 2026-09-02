"""System domain: GPU, OS info, shutdown, timer, notes, clipboard, brightness, weather, media control."""

import os
import glob
import subprocess
import shutil
import time
import json
from datetime import datetime
from pathlib import Path

from mcp_common.paths import HOME, format_size
from mcp_common.logging import log_operation
from mcp_common.audit import record_system_error

NOTES_DIR = os.path.join(HOME, ".notes")


def capture_desktop_screen(target_path: str = None) -> str:
    """Captura de pantalla silenciosa y ultra-rápida (0 Popups, 0.05s)."""
    dest = Path(target_path) if target_path else Path(HOME) / "Pictures/screenshots" / f"screenshot_{int(time.time())}.png"
    dest.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    if "DISPLAY" not in env:
        env["DISPLAY"] = ":1" if os.path.exists("/tmp/.X11-unix/X1") else ":0"

    if shutil.which("maim"):
        try:
            res = subprocess.run(["maim", str(dest)], env=env, capture_output=True, timeout=4)
            if dest.exists() and dest.stat().st_size > 0:
                return str(dest)
        except Exception:
            pass

    if shutil.which("cosmic-screenshot"):
        try:
            res = subprocess.run([
                "cosmic-screenshot",
                "--interactive=false",
                "--notify=false",
                "--save-dir", str(dest.parent)
            ], env=env, capture_output=True, text=True, timeout=5)
            out_file = res.stdout.strip()
            if out_file and os.path.exists(out_file):
                if out_file != str(dest):
                    shutil.move(out_file, str(dest))
                return str(dest)
            import glob
            pngs = sorted(glob.glob(str(dest.parent / "Screenshot_*.png")), key=os.path.getmtime, reverse=True)
            if pngs and os.path.exists(pngs[0]):
                if pngs[0] != str(dest):
                    shutil.move(pngs[0], str(dest))
                return str(dest)
        except Exception:
            pass

    if shutil.which("import"):
        try:
            res = subprocess.run(["import", "-window", "root", str(dest)], env=env, capture_output=True, timeout=4)
            if dest.exists() and dest.stat().st_size > 0:
                return str(dest)
        except Exception:
            pass

    if shutil.which("gnome-screenshot"):
        try:
            res = subprocess.run(["gnome-screenshot", "-f", str(dest)], env=env, capture_output=True, timeout=4)
            if dest.exists() and dest.stat().st_size > 0:
                return str(dest)
        except Exception:
            pass

    return None


TOOLS = [
    {
        "name": "get_system_info",
        "description": "Obtiene información del sistema: CPU, RAM, disco, OS, uptime.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "get_gpu_status",
        "description": "Obtiene estado de la GPU NVIDIA: VRAM, uso, temperatura, procesos.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "system_shutdown",
        "description": "Apaga o reinicia el sistema. REQUIERE CONFIRMACIÓN.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["shutdown", "reboot", "suspend", "hibernate"], "description": "Acción del sistema."},
                "delay": {"type": "integer", "description": "Delay en segundos (default: 0 = inmediato)."},
                "confirm": {"type": "boolean", "description": "Confirmar acción destructiva."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "timer",
        "description": "Crea un temporizador o alarma. Notifica cuando termina.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "minutes": {"type": "integer", "description": "Duración en minutos."},
                "message": {"type": "string", "description": "Mensaje de notificación cuando termine."}
            },
            "required": ["minutes", "message"]
        }
    },
    {
        "name": "notes",
        "description": "Gestiona notas rápidas en ~/.notes/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["create", "list", "read", "delete"], "description": "Acción a ejecutar."},
                "title": {"type": "string", "description": "Título de la nota."},
                "content": {"type": "string", "description": "Contenido de la nota (para create)."},
                "category": {"type": "string", "enum": ["General", "Trabajo", "Personal", "Tasks"], "description": "Categoría. Default: General."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "clipboard",
        "description": "Copia o pega texto del clipboard del sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["copy", "paste", "clear"], "description": "Acción."},
                "text": {"type": "string", "description": "Texto a copiar (requerido para copy)."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "brightness",
        "description": "Controla el brillo de la pantalla.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["get", "set", "up", "down"], "description": "Acción."},
                "level": {"type": "integer", "description": "Nivel de brillo (0-100) para set."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "weather",
        "description": "Obtiene el clima actual de una ciudad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "Nombre de la ciudad. Default: ubicación automática."}
            },
            "required": []
        }
    },
    {
        "name": "open_url",
        "description": "Abre una URL en el navegador Brave.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL a abrir."}
            },
            "required": ["url"]
        }
    },
    {
        "name": "media_control",
        "description": "Controla reproducción de música: play, pause, next, previous, volume.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["play", "pause", "next", "previous", "volume_up", "volume_down", "mute", "get_status"], "description": "Acción."}
            },
            "required": ["action"]
        }
    },
    {
        "name": "screenshot",
        "description": "Captura una screenshot de la pantalla. Guarda en ~/Pictures/screenshots/.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre del archivo (sin extensión). Default: timestamp."
                },
                "delay": {
                    "type": "integer",
                    "description": "Delay en segundos antes de capturar. Default: 0."
                }
            },
            "required": []
        }
    },
    {
        "name": "process_list",
        "description": "Lista procesos activos del sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sort_by": {
                    "type": "string",
                    "enum": ["cpu", "memory", "pid", "name"],
                    "description": "Ordenar por. Default: cpu."
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de procesos. Default: 20."
                }
            },
            "required": []
        }
    },
    {
        "name": "process_kill",
        "description": "Termina un proceso por PID o nombre. REQUIERE CONFIRMACIÓN.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pid": {
                    "type": "integer",
                    "description": "PID del proceso a terminar."
                },
                "name": {
                    "type": "string",
                    "description": "Nombre del proceso a terminar."
                },
                "signal": {
                    "type": "string",
                    "enum": ["TERM", "KILL", "HUP", "INT"],
                    "description": "Señal a enviar. Default: TERM."
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Confirmar acción destructiva."
                }
            },
            "required": []
        }
    },
    {
        "name": "process_search",
        "description": "Busca procesos por nombre.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nombre o parte del nombre del proceso."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "cron_list",
        "description": "Lista tareas programadas (cron jobs) del usuario.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "cron_add",
        "description": "Agrega una tarea programada (cron job).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "schedule": {
                    "type": "string",
                    "description": "Horario en formato cron (ej: '0 */2 * * *' = cada 2 horas)."
                },
                "command": {
                    "type": "string",
                    "description": "Comando a ejecutar."
                },
                "description": {
                    "type": "string",
                    "description": "Descripción de la tarea."
                }
            },
            "required": ["schedule", "command"]
        }
    },
    {
        "name": "cron_delete",
        "description": "Elimina una tarea programada por línea.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "line_number": {
                    "type": "integer",
                    "description": "Número de línea del cron job a eliminar."
                }
            },
            "required": ["line_number"]
        }
    },
    {
        "name": "monitor_realtime",
        "description": "Muestra métricas del sistema en tiempo real (una captura).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "metrics": {
                    "type": "string",
                    "description": "Métricas a mostrar: 'all', 'cpu', 'memory', 'disk', 'network'. Default: all."
                }
            },
            "required": []
        }
    },
    {
        "name": "monitor_top_processes",
        "description": "Muestra los procesos que más CPU/RAM consumen.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "by": {
                    "type": "string",
                    "enum": ["cpu", "memory"],
                    "description": "Ordenar por CPU o memoria. Default: cpu."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de procesos. Default: 10."
                }
            },
            "required": []
        }
    },
    {
        "name": "disk_usage",
        "description": "Muestra uso de disco en todas las particiones.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "disk_io",
        "description": "Muestra estadísticas de I/O de disco.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
]


# ── Handlers ───────────────────────────────────────────────

def _get_system_info(args):
    info = []
    try:
        with open("/etc/os-release") as f:
            for line in f:
                if line.startswith("PRETTY_NAME"):
                    info.append(f"SO: {line.split('=', 1)[1].strip().strip('\"')}")
                    break
    except Exception:
        pass

    try:
        uptime_s = float(open("/proc/uptime").read().split()[0])
        days = int(uptime_s // 86400)
        hours = int((uptime_s % 86400) // 3600)
        mins = int((uptime_s % 3600) // 60)
        info.append(f"Uptime: {days}d {hours}h {mins}m")
    except Exception:
        pass

    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if "model name" in line:
                    info.append(f"CPU: {line.split(':', 1)[1].strip()}")
                    break
        info.append(f"Cores: {os.cpu_count()}")
    except Exception:
        pass

    try:
        result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split("\n"):
            if line.startswith("Mem:"):
                parts = line.split()
                total, used, free = int(parts[1]), int(parts[2]), int(parts[3])
                info.append(f"RAM: {used}MB / {total}MB ({free}MB libre)")
                break
    except Exception:
        pass

    try:
        result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
        lines = result.stdout.strip().split("\n")
        if len(lines) > 1:
            parts = lines[1].split()
            info.append(f"Disco: {parts[2]} / {parts[1]} ({parts[4]} usado)")
    except Exception:
        pass

    try:
        with open("/proc/loadavg") as f:
            load = f.read().split()[:3]
            info.append(f"Load: {' '.join(load)}")
    except Exception:
        pass

    return "\n".join(info) if info else "No se pudo obtener información del sistema"


def _get_gpu_status(args):
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.used,memory.total,temperature.gpu,utilization.gpu,utilization.memory,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return f"Error nvidia-smi: {result.stderr}"

        lines = result.stdout.strip().split("\n")
        info = ["🖥️ GPU NVIDIA:\n"]
        for i, line in enumerate(lines):
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 7:
                info.append(f"  GPU {i}: {parts[0]}")
                info.append(f"  VRAM: {parts[1]}MB / {parts[2]}MB")
                info.append(f"  Temperatura: {parts[3]}°C")
                info.append(f"  Uso GPU: {parts[4]}%")
                info.append(f"  Uso Memoria: {parts[5]}%")
                info.append(f"  Consumo: {parts[6]}W")

        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-compute-apps=pid,name,used_memory", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            if result.stdout.strip():
                info.append(f"\n  Procesos GPU:")
                for line in result.stdout.strip().split("\n"):
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) >= 3:
                        info.append(f"    PID {parts[0]}: {parts[1]} ({parts[2]}MB)")
        except Exception:
            pass

        return "\n".join(info)
    except FileNotFoundError:
        return "Error: nvidia-smi no encontrado. ¿GPU NVIDIA instalada?"
    except Exception as e:
        return f"Error obteniendo GPU status: {e}"


def _system_shutdown(args):
    action = args["action"]
    delay = args.get("delay", 0)
    confirm = args.get("confirm", False)

    if not confirm:
        return f"⚠️ Acción destructiva: {action}. Responde con confirm=true para ejecutar."

    valid_actions = {"shutdown", "reboot", "suspend", "hibernate"}
    if action not in valid_actions:
        return f"Acción no reconocida: {action}. Usar: {', '.join(sorted(valid_actions))}"

    try:
        if action == "shutdown":
            delay_min = delay // 60 if delay >= 60 else 0
            cmd = ["shutdown", "-h", f"+{delay_min}" if delay_min > 0 else "now"]
        elif action == "reboot":
            delay_min = delay // 60 if delay >= 60 else 0
            cmd = ["shutdown", "-r", f"+{delay_min}" if delay_min > 0 else "now"]
        elif action == "suspend":
            cmd = ["systemctl", "suspend"]
        elif action == "hibernate":
            cmd = ["systemctl", "hibernate"]

        subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        log_operation("system_shutdown", {"action": action}, "executed")
        return f"✅ {action} ejecutado"
    except Exception as e:
        return f"Error en {action}: {e}"


def _timer(args):
    minutes = args["minutes"]
    message = args["message"]
    try:
        seconds = minutes * 60
        safe_msg = json.dumps(message)
        timer_script = f"""
import time
import subprocess
import json
time.sleep({seconds})
subprocess.run(['notify-send', 'Temporizador', json.loads({safe_msg})])
"""
        subprocess.Popen(
            ["python3", "-c", timer_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        log_operation("timer", {"minutes": minutes, "message": message}, "started")
        return f"⏱️ Temporizador iniciado: {minutes} minutos\nMensaje: {message}"
    except Exception as e:
        return f"Error creando temporizador: {e}"


def _notes(args):
    action = args["action"]
    title = args.get("title")
    content = args.get("content")
    category = args.get("category", "General")

    try:
        notes_cat_dir = os.path.join(NOTES_DIR, category)
        os.makedirs(notes_cat_dir, exist_ok=True)

        if action == "create":
            if not title:
                return "Error: Se requiere título para crear nota"
            if not content:
                return "Error: Se requiere contenido para crear nota"
            filename = f"{title.replace(' ', '_').replace('/', '_')}.md"
            filepath = os.path.join(notes_cat_dir, filename)
            with open(filepath, "w") as f:
                f.write(f"# {title}\n\n{content}\n")
            log_operation("notes", {"action": "create", "title": title}, filepath)
            return f"📝 Nota creada: {category}/{filename}"

        elif action == "list":
            files = sorted(glob.glob(os.path.join(notes_cat_dir, "*.md")))
            if not files:
                return f"No hay notas en {category}"
            lines = [f"📝 Notas en {category}:\n"]
            for f in files[:20]:
                name = os.path.basename(f).replace(".md", "").replace("_", " ")
                size = format_size(os.path.getsize(f))
                lines.append(f"  • {name} ({size})")
            return "\n".join(lines)

        elif action == "read":
            if not title:
                return "Error: Se requiere título para leer nota"
            filename = f"{title.replace(' ', '_').replace('/', '_')}.md"
            filepath = os.path.join(notes_cat_dir, filename)
            if not os.path.exists(filepath):
                return f"Error: Nota no encontrada: {title}"
            with open(filepath) as f:
                note_content = f.read()
            return f"📝 {title}\n\n{note_content}"

        elif action == "delete":
            if not title:
                return "Error: Se requiere título para eliminar nota"
            filename = f"{title.replace(' ', '_').replace('/', '_')}.md"
            filepath = os.path.join(notes_cat_dir, filename)
            if not os.path.exists(filepath):
                return f"Error: Nota no encontrada: {title}"
            os.remove(filepath)
            log_operation("notes", {"action": "delete", "title": title}, "deleted")
            return f"🗑️ Nota eliminada: {title}"

        else:
            return f"Acción no reconocida: {action}"
    except Exception as e:
        return f"Error con notas: {e}"


def _clipboard(args):
    action = args["action"]
    text = args.get("text")

    try:
        if action == "copy":
            if not text:
                return "Error: Se requiere texto para copiar"
            subprocess.run(["xclip", "-selection", "clipboard"], input=text.encode(), capture_output=True, timeout=5)
            log_operation("clipboard", {"action": "copy"}, text[:50])
            return f"📋 Copiado al clipboard: {text[:100]}"
        elif action == "paste":
            result = subprocess.run(["xclip", "-selection", "clipboard", "-o"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0 and result.stdout:
                return f"📋 Clipboard: {result.stdout}"
            return "Clipboard vacío"
        elif action == "clear":
            subprocess.run(["xclip", "-selection", "clipboard"], input=b"", capture_output=True, timeout=5)
            return "📋 Clipboard limpiado"
        else:
            return f"Acción no reconocida: {action}"
    except FileNotFoundError:
        return "Error: xclip no encontrado"
    except Exception as e:
        return f"Error con clipboard: {e}"


def _brightness(args):
    action = args["action"]
    level = args.get("level")

    try:
        backlight_path = "/sys/class/backlight"
        if not os.path.exists(backlight_path):
            return "Error: No se encontró control de brillo"
        devices = os.listdir(backlight_path)
        if not devices:
            return "Error: No hay dispositivos de brillo"

        device = devices[0]
        max_bright_file = os.path.join(backlight_path, device, "max_brightness")
        bright_file = os.path.join(backlight_path, device, "brightness")

        with open(max_bright_file) as f:
            max_brightness = int(f.read().strip())

        if action == "get":
            with open(bright_file) as f:
                current = int(f.read().strip())
            pct = int((current / max_brightness) * 100)
            return f"☀️ Brillo actual: {pct}% ({current}/{max_brightness})"
        elif action == "set":
            if level is None:
                return "Error: Se requiere nivel para set"
            level = max(0, min(100, level))
            new_b = int((level / 100) * max_brightness)
            subprocess.run(["tee", bright_file], input=str(new_b).encode(), timeout=5)
            return f"☀️ Brillo establecido a {level}%"
        elif action == "up":
            with open(bright_file) as f:
                current = int(f.read().strip())
            inc = max(1, max_brightness // 20)
            new_b = min(max_brightness, current + inc)
            subprocess.run(["tee", bright_file], input=str(new_b).encode(), timeout=5)
            return f"☀️ Brillo subido a {int((new_b / max_brightness) * 100)}%"
        elif action == "down":
            with open(bright_file) as f:
                current = int(f.read().strip())
            dec = max(1, max_brightness // 20)
            new_b = max(0, current - dec)
            subprocess.run(["tee", bright_file], input=str(new_b).encode(), timeout=5)
            return f"☀️ Brillo bajado a {int((new_b / max_brightness) * 100)}%"
        else:
            return f"Acción no reconocida: {action}"
    except PermissionError:
        return "Error: Sin permisos para cambiar brillo"
    except Exception as e:
        return f"Error controlando brillo: {e}"


def _weather(args):
    city = args.get("city")
    try:
        url = f"https://wttr.in/{city}?format=%l:+%C+%t+%h+%w" if city else "https://wttr.in/?format=%l:+%C+%t+%h+%w"
        result = subprocess.run(["curl", "-s", "--max-time", "10", url], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"Error obteniendo clima: {result.stderr}"
        weather_info = result.stdout.strip()
        if not weather_info or "Unknown" in weather_info:
            return f"No se pudo obtener el clima para: {city or 'ubicación actual'}"
        log_operation("weather", {"city": city}, weather_info[:50])
        return f"🌤️ Clima: {weather_info}"
    except subprocess.TimeoutExpired:
        return "Timeout obteniendo clima"
    except Exception as e:
        return f"Error obteniendo clima: {e}"


def _open_url(args):
    url = args["url"]
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        subprocess.Popen(["brave-browser", "--new-tab", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        log_operation("open_url", {"url": url}, "opened")
        return f"🌐 Abriendo: {url}"
    except Exception as e:
        return f"Error abriendo URL: {e}"


def _media_control(args):
    action = args["action"]
    try:
        if action == "get_status":
            result = subprocess.run(["playerctl", "status"], capture_output=True, text=True, timeout=5)
            if result.returncode != 0:
                return "No hay reproducción activa"
            status = result.stdout.strip()
            result = subprocess.run(["playerctl", "metadata", "title"], capture_output=True, text=True, timeout=5)
            title = result.stdout.strip() if result.returncode == 0 else "Desconocido"
            result = subprocess.run(["playerctl", "metadata", "artist"], capture_output=True, text=True, timeout=5)
            artist = result.stdout.strip() if result.returncode == 0 else "Desconocido"
            return f"🎵 {status}: {title} - {artist}"
        elif action == "play":
            subprocess.run(["playerctl", "play"], capture_output=True, timeout=5)
            return "▶️ Reproduciendo"
        elif action == "pause":
            subprocess.run(["playerctl", "pause"], capture_output=True, timeout=5)
            return "⏸️ Pausado"
        elif action == "next":
            subprocess.run(["playerctl", "next"], capture_output=True, timeout=5)
            return "⏭️ Siguiente"
        elif action == "previous":
            subprocess.run(["playerctl", "previous"], capture_output=True, timeout=5)
            return "⏮️ Anterior"
        elif action == "volume_up":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "5%+"], capture_output=True, timeout=5)
            return "🔊 Volumen subido"
        elif action == "volume_down":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "5%-"], capture_output=True, timeout=5)
            return "🔉 Volumen bajado"
        elif action == "mute":
            subprocess.run(["amixer", "-D", "pulse", "sset", "Master", "toggle"], capture_output=True, timeout=5)
            return "🔇 Mute toggle"
        else:
            return f"Acción no reconocida: {action}"
    except FileNotFoundError:
        return "Error: playerctl o amixer no encontrado"
    except Exception as e:
        return f"Error en media control: {e}"


def _screenshot(args):
    filename = args.get("filename")
    delay = args.get("delay", 0)
    try:
        screenshots_dir = os.path.join(HOME, "Pictures/screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        if not filename:
            filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        if not filename.endswith(".png"):
            filename += ".png"

        filepath = os.path.join(screenshots_dir, filename)

        if delay > 0:
            time.sleep(delay)

        captured_path = capture_desktop_screen(filepath)

        if captured_path and os.path.exists(captured_path) and os.path.getsize(captured_path) > 0:
            size = format_size(os.path.getsize(captured_path))
            log_operation("screenshot", {"filename": filename}, f"saved {size}")

            ocr_text = ""
            if shutil.which("tesseract"):
                try:
                    ocr_proc = subprocess.run(
                        ["tesseract", captured_path, "stdout", "-l", "spa+eng"],
                        capture_output=True,
                        text=True,
                        timeout=6
                    )
                    clean_ocr = ocr_proc.stdout.strip()
                    if clean_ocr:
                        ocr_text = f"\n\n🔍 **Contenido e Interfaz Visual Detectados en Pantalla (OCR):**\n```text\n{clean_ocr[:1500]}\n```"
                except Exception:
                    pass

            return (
                f"📸 **Captura de pantalla realizada exitosamente:** `{captured_path}` ({size})"
                f"{ocr_text}\n\n"
                f"💡 *Para renderizar la imagen directamente en la interfaz del chat, ejecuta `media_view(file_path=\"{captured_path}\")`.*"
            )

        return "Error: No se pudo crear la screenshot (Compositor Wayland/X11 no accesible)"

    except Exception as e:
        return f"Error creando screenshot: {e}"


def _process_list(args):
    sort_by = args.get("sort_by", "cpu")
    limit = args.get("limit", 20)
    valid_sort = {"cpu": "-%cpu", "memory": "-%mem"}
    sort_flag = valid_sort.get(sort_by, None)
    try:
        cmd = ["ps", "aux"]
        if sort_flag:
            cmd = ["ps", "aux", f"--sort={sort_flag}"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return "Error obteniendo procesos"

        lines = result.stdout.strip().split("\n")
        processes = lines[1:limit+1]

        output = [f"📊 Procesos (por {sort_by}):\n"]
        output.append(f"{'PID':>8} {'CPU%':>6} {'MEM%':>6} {'COMMAND'}")
        output.append("-" * 50)

        for proc in processes:
            parts = proc.split(None, 10)
            if len(parts) >= 11:
                pid = parts[1]
                cpu = parts[2]
                mem = parts[3]
                cmd = parts[10][:40]
                output.append(f"{pid:>8} {cpu:>6} {mem:>6} {cmd}")

        return "\n".join(output)

    except Exception as e:
        return f"Error obteniendo procesos: {e}"


def _process_kill(args):
    import re as _re
    pid = args.get("pid")
    name = args.get("name")
    signal = args.get("signal", "TERM")
    confirm = args.get("confirm", False)

    valid_signals = {"TERM", "KILL", "HUP", "INT", "QUIT", "USR1", "USR2"}
    if signal not in valid_signals:
        return f"Error: Señal no válida. Usar: {', '.join(sorted(valid_signals))}"

    if not confirm:
        target = f"PID {pid}" if pid else f"proceso {name}"
        return f"⚠️ Acción destructiva: terminar {target} con señal {signal}. Responde con confirm=true."

    if pid and not _re.match(r"^\d+$", str(pid)):
        return "Error: PID debe ser numérico"
    if name and not _re.match(r"^[a-zA-Z0-9_\.\-]+$", name):
        return "Error: Nombre de proceso contiene caracteres no válidos"

    try:
        if pid:
            cmd = ["kill", f"-{signal}", str(pid)]
        elif name:
            cmd = ["pkill", f"-{signal}", name]
        else:
            return "Error: Se requiere PID o nombre"

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return f"Error terminando proceso: {result.stderr}"

        target = f"PID {pid}" if pid else f"proceso {name}"
        log_operation("process_kill", {"pid": pid, "name": name, "signal": signal}, "killed")
        return f"✅ {target} terminado con señal {signal}"

    except Exception as e:
        return f"Error terminando proceso: {e}"


def _process_search(args):
    query = args["query"]
    try:
        result = subprocess.run(
            ["pgrep", "-f", query],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return f"No se encontraron procesos para: {query}"

        pids = result.stdout.strip().split("\n")
        lines = [f"🔍 Procesos para '{query}' ({len(pids)} encontrados):\n"]

        for pid in pids[:10]:
            if pid:
                info = subprocess.run(
                    ["ps", "-p", pid, "-o", "pid,pcpu,pmem,comm"],
                    capture_output=True, text=True, timeout=5
                )
                if info.returncode == 0:
                    lines.append(info.stdout.strip())

        return "\n".join(lines)

    except Exception as e:
        return f"Error buscando procesos: {e}"


def _cron_list(args):
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            return "No hay tareas programadas"

        lines = result.stdout.strip().split("\n")
        lines = [l for l in lines if l.strip() and not l.startswith("#")]

        if not lines:
            return "No hay tareas programadas"

        output = [f"📅 Tareas programadas ({len(lines)}):\n"]
        for i, line in enumerate(lines, 1):
            output.append(f"  {i}. {line}")

        return "\n".join(output)

    except Exception as e:
        return f"Error listando cron jobs: {e}"


def _cron_add(args):
    schedule = args["schedule"]
    command = args["command"]
    description = args.get("description")
    try:
        cron_line = f"{schedule} {command}"
        if description:
            cron_line = f"# {description}\n{schedule} {command}"

        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, timeout=5
        )

        existing = result.stdout if result.returncode == 0 else ""
        new_crontab = existing + "\n" + cron_line + "\n"

        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True, text=True, timeout=5
        )

        if proc.returncode != 0:
            return f"Error agregando cron job: {proc.stderr}"

        log_operation("cron_add", {"schedule": schedule, "command": command}, "added")
        return f"✅ Cron job agregado: {schedule} → {command}"

    except Exception as e:
        return f"Error agregando cron job: {e}"


def _cron_delete(args):
    line_number = args["line_number"]
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            return "No hay tareas programadas"

        lines = result.stdout.strip().split("\n")
        active_lines = [l for l in lines if l.strip() and not l.startswith("#")]

        if line_number < 1 or line_number > len(active_lines):
            return f"Error: Número de línea inválido (1-{len(active_lines)})"

        line_to_delete = active_lines[line_number - 1]

        new_lines = []
        for line in lines:
            if line.strip() == line_to_delete.strip():
                continue
            new_lines.append(line)

        new_crontab = "\n".join(new_lines) + "\n"

        proc = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True, text=True, timeout=5
        )

        if proc.returncode != 0:
            return f"Error eliminando cron job: {proc.stderr}"

        log_operation("cron_delete", {"line_number": line_number}, "deleted")
        return f"✅ Cron job eliminado: {line_to_delete}"

    except Exception as e:
        return f"Error eliminando cron job: {e}"


def _monitor_realtime(args):
    metrics = args.get("metrics", "all")
    try:
        output = ["📊 Métricas del sistema:\n"]

        if metrics in ["all", "cpu"]:
            with open("/proc/loadavg") as f:
                load = f.read().split()[:3]
                output.append(f"  CPU Load: {' '.join(load)}")

            with open("/proc/stat") as f:
                cpu = f.readline().split()
                idle = int(cpu[4])
                total = sum(int(x) for x in cpu[1:])
                usage = round((1 - idle/total) * 100, 1)
                output.append(f"  CPU Usage: {usage}%")

        if metrics in ["all", "memory"]:
            result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
            for line in result.stdout.split("\n"):
                if line.startswith("Mem:"):
                    parts = line.split()
                    total = int(parts[1])
                    used = int(parts[2])
                    usage = round(used/total*100, 1)
                    output.append(f"  Memory: {used}MB / {total}MB ({usage}%)")
                    break

        if metrics in ["all", "disk"]:
            result = subprocess.run(["df", "-h", "/"], capture_output=True, text=True, timeout=5)
            lines = result.stdout.strip().split("\n")
            if len(lines) > 1:
                parts = lines[1].split()
                output.append(f"  Disk: {parts[2]} / {parts[1]} ({parts[4]})")

        if metrics in ["all", "network"]:
            with open("/proc/net/dev") as f:
                for line in f:
                    if "eth0" in line or "wlan0" in line:
                        parts = line.split()
                        rx = int(parts[1]) / 1024 / 1024
                        tx = int(parts[9]) / 1024 / 1024
                        output.append(f"  Network: RX={rx:.1f}MB TX={tx:.1f}MB")
                        break

        return "\n".join(output)

    except Exception as e:
        return f"Error obteniendo métricas: {e}"


def _monitor_top_processes(args):
    by = args.get("by", "cpu")
    limit = args.get("limit", 10)
    try:
        sort_flag = "-%cpu" if by == "cpu" else "-%mem"
        cmd = ["ps", "aux", f"--sort={sort_flag}"]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return "Error obteniendo procesos"

        lines = result.stdout.strip().split("\n")
        processes = lines[1:limit+1]

        output = [f"📊 Top {limit} procesos por {by}:\n"]
        output.append(f"{'PID':>8} {'CPU%':>6} {'MEM%':>6} {'COMMAND'}")
        output.append("-" * 50)

        for proc in processes:
            parts = proc.split(None, 10)
            if len(parts) >= 11:
                pid = parts[1]
                cpu = parts[2]
                mem = parts[3]
                cmd = parts[10][:35]
                output.append(f"{pid:>8} {cpu:>6} {mem:>6} {cmd}")

        return "\n".join(output)

    except Exception as e:
        return f"Error obteniendo top procesos: {e}"


def _disk_usage(args):
    try:
        result = subprocess.run(
            ["df", "-h", "--output=source,size,used,avail,pcent,target"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return "Error obteniendo uso de disco"

        lines = result.stdout.strip().split("\n")
        output = ["💾 Uso de disco:\n"]
        output.append(lines[0])

        for line in lines[1:]:
            if line.startswith("/dev/"):
                output.append(line)

        return "\n".join(output)

    except Exception as e:
        return f"Error obteniendo uso de disco: {e}"


def _disk_io(args):
    try:
        result = subprocess.run(
            ["iostat", "-d", "1", "1"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return "Error obteniendo I/O de disco"

        lines = result.stdout.strip().split("\n")
        output = ["💿 I/O de Disco:\n"]

        for line in lines:
            if line and not line.startswith("Linux") and not line.startswith("Device"):
                parts = line.split()
                if len(parts) >= 4:
                    output.append(f"  {parts[0]}: Read={parts[1]} KB/s, Write={parts[2]} KB/s")

        return "\n".join(output) if len(output) > 1 else "No hay datos de I/O disponibles"

    except FileNotFoundError:
        return "Error: iostat no instalado (instalar sysstat)"
    except Exception as e:
        return f"Error obteniendo I/O: {e}"


HANDLERS = {
    "get_system_info": _get_system_info,
    "get_gpu_status": _get_gpu_status,
    "system_shutdown": _system_shutdown,
    "timer": _timer,
    "notes": _notes,
    "clipboard": _clipboard,
    "brightness": _brightness,
    "weather": _weather,
    "open_url": _open_url,
    "media_control": _media_control,
    "screenshot": _screenshot,
    "process_list": _process_list,
    "process_kill": _process_kill,
    "process_search": _process_search,
    "cron_list": _cron_list,
    "cron_add": _cron_add,
    "cron_delete": _cron_delete,
    "monitor_realtime": _monitor_realtime,
    "monitor_top_processes": _monitor_top_processes,
    "disk_usage": _disk_usage,
    "disk_io": _disk_io,
}
