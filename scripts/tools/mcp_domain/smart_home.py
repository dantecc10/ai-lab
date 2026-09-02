"""Smart home, automation, reminders, dev-ops control, GitHub monitor, media, creative voice, and image generation."""

import os
import sys
import subprocess
import asyncio

import time
from pathlib import Path



# Add venv site-packages
skills_venv = os.path.expanduser("~/scripting/gpu-tools/skills/.venv/lib/python3.12/site-packages")
if os.path.exists(skills_venv) and skills_venv not in sys.path:
    sys.path.insert(0, skills_venv)

# ── Kasa Smart Plugs ──────────────────────────────────────
KASA_DEVICES = {
    "elektrodante": "192.168.1.66",
    "lux": "192.168.1.67"
}

KASA_ALIASES = {
    "luz": "lux",
    "foco": "lux",
    "lampara": "lux",
    "electro": "elektrodante",
    "escritorio": "elektrodante",
    "pc": "elektrodante"
}

TOOLS = [
    # ── Kasa Smart Plugs ─────────────────────────────────────
    {
        "name": "kasa_set_plug_state",
        "description": "Enciende o apaga uno o todos los enchufes inteligentes Kasa (ElektroDante, Lux, o 'todos').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "Nombre del dispositivo ('elektrodante', 'lux', 'todos', o alias: 'luz', 'escritorio', 'pc')."
                },
                "turn_on": {
                    "type": "boolean",
                    "description": "True para encender, False para apagar."
                }
            },
            "required": ["device_name", "turn_on"]
        }
    },
    {
        "name": "kasa_get_plugs_status",
        "description": "Obtiene el estado actual (encendido/apagado) de todos los enchufes inteligentes Kasa.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    # ── Automation, Nighttime & Visual Alerts ─────────────────
    {
        "name": "control_keyboard_backlight",
        "description": "Controla el brillo de la luz del teclado ASUS ROG/TUF ('off', 'low', 'med', 'high'). Útil para apagar la luz del teclado al dormir.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "string",
                    "enum": ["off", "low", "med", "high"],
                    "description": "Nivel de brillo ('off', 'low', 'med', 'high')"
                }
            },
            "required": ["level"]
        }
    },
    {
        "name": "trigger_visual_alert",
        "description": "Control de efectos e iluminación libre del teclado ASUS ROG/TUF y lámpara: reproduce secuencias cromáticas personalizadas, estilos temáticos ('cyberpunk', 'police', 'matrix', 'rainbow', 'fire', 'aurora', 'heartbeat', 'synthwave', 'breathe', 'strobe'), listas libres de colores RGB, intervalos de velocidad y presets. Siempre retorna al color base Cian (#00ffff).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "style": {
                    "type": "string",
                    "enum": ["police", "cyberpunk", "synthwave", "matrix", "rainbow", "fire", "aurora", "heartbeat", "breathe", "strobe"],
                    "description": "Estilo temático de animación (opcional)"
                },
                "colors": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista libre de colores hex o nombres (ej: ['ff0000', '00ffff', 'ff00ff'] o ['red', 'blue'])"
                },
                "level": {
                    "type": "string",
                    "enum": ["normal", "important", "critical", "error", "success", "warning"],
                    "description": "Preset de severidad/prioridad ('normal': cian, 'important': ámbar, 'critical': rojo, 'success': verde)"
                },
                "duration": {
                    "type": "number",
                    "description": "Duración total en segundos (ej: 2.5, 5.0, 10.0)"
                },
                "speed_ms": {
                    "type": "integer",
                    "description": "Intervalo entre cambios en milisegundos (ej: 60ms para rápido, 200ms para lento)"
                },
                "include_lamp": {
                    "type": "boolean",
                    "description": "Si debe incluir parpadeo de la lámpara Lux"
                }
            }
        }
    },
    {
        "name": "execute_sleep_routine",
        "description": "Ejecuta la rutina nocturna de dormir: Apaga la luz Lux, deja encendido ElektroDante para cargar dispositivos en la noche, y apaga la luz del teclado (o apaga la computadora entera si se le solicita).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "shutdown_pc": {
                    "type": "boolean",
                    "description": "True si el usuario se despide para apagar la computadora (ej. 'Adiós, nos vemos mañana', 'Vámonos a dormir'). False si solo es hora de dormir manteniendo la compu encendida (ej. 'Es hora de dormir')."
                }
            },
            "required": ["shutdown_pc"]
        }
    },
    # ── Dev Ops & Control Remoto ─────────────────────────────
    {
        "name": "dev_system_telemetry",
        "description": "Dashboard completo de telemetría en tiempo real: GPU NVIDIA VRAM/temp/potencia, RAM, Swap, Disco, y estado de servicios IA activos.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "dev_service_control",
        "description": "Gestiona servicios systemd del ecosistema (gemma4-server, e4b-server, whisper-server, telegram-bot, git-sentinel, chatmanager).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_name": {"type": "string", "description": "Nombre del servicio systemd"},
                "action": {"type": "string", "enum": ["start", "stop", "restart", "status", "logs"], "description": "Acción a realizar"}
            },
            "required": ["service_name", "action"]
        }
    },
    {
        "name": "dev_process_monitor",
        "description": "Monitorea los procesos con mayor consumo de CPU y memoria RAM en el sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "count": {"type": "integer", "description": "Número de procesos a listar", "default": 5}
            }
        }
    },
    {
        "name": "dev_git_quick_action",
        "description": "Ejecuta comandos git (status, diff, log, branch, pull) en cualquier repositorio del acervo en /media/darkseid/DATA/Repos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_path_or_name": {"type": "string", "description": "Nombre de la carpeta o ruta del repositorio"},
                "git_command": {"type": "string", "description": "Comando git a ejecutar (ej: 'status', 'log', 'diff', 'branch', 'pull')", "default": "status"}
            },
            "required": ["repo_path_or_name"]
        }
    },
    {
        "name": "audit_git_repositories",
        "description": "Audita y revisa todos los repositorios de código en /media/darkseid/DATA/Repos para detectar cambios sin commitear, archivos nuevos o commits locales sin subir a GitHub/remoto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "base_dir": {
                    "type": "string",
                    "description": "Directorio raíz de repositorios (por defecto '/media/darkseid/DATA/Repos')"
                }
            }
        }
    },
    # ── GitHub Monitor Tools ─────────────────────────────────
    {
        "name": "github_monitor_status",
        "description": "Obtiene el estado de la telemetría del monitor permanente de GitHub: repositorios activos, commits recientes, estado de CI/CD (GitHub Actions) y alertas enviadas.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "github_watch_repo",
        "description": "Agrega un repositorio específico de GitHub al monitoreo permanente en segundo plano.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "Nombre del repositorio en formato 'propietario/nombre' (ej: 'dantecc10/ai-lab')."
                }
            },
            "required": ["repo_name"]
        }
    },
    {
        "name": "github_unwatch_repo",
        "description": "Desactiva el monitoreo de un repositorio de GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "Nombre del repositorio (ej: 'dantecc10/ai-lab')."
                }
            },
            "required": ["repo_name"]
        }
    },
    {
        "name": "github_actions_status",
        "description": "Consulta el estado detallado de los últimos flujos de trabajo y builds de GitHub Actions para un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo_name": {
                    "type": "string",
                    "description": "Nombre del repositorio (ej: 'dantecc10/ai-lab'). Si no se especifica, usa 'dantecc10/ai-lab'.",
                    "default": "dantecc10/ai-lab"
                }
            }
        }
    },
    # ── Multimedia & YouTube (Whisper + yt-dlp) ──────────────────
    {
        "name": "media_download_url",
        "description": "Descarga audio o video de YouTube, X, TikTok, Reddit o Podcasts mediante yt-dlp.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "URL del contenido a descargar"},
                "media_type": {"type": "string", "enum": ["audio", "video"], "description": "Tipo de descarga ('audio' mp3 o 'video' mp4)", "default": "audio"}
            },
            "required": ["url"]
        }
    },
    {
        "name": "media_transcribe_audio",
        "description": "Transcribe audio local o video de YouTube extrayendo el habla con Whisper STT (:9093).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url_or_path": {"type": "string", "description": "Ruta a archivo de audio local o URL de YouTube"}
            },
            "required": ["url_or_path"]
        }
    },
    {
        "name": "media_summarize_content",
        "description": "Descarga, transcribe con Whisper y genera un resumen estructurado de alto valor con Gemma 4 para un video de YouTube, podcast o audio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url_or_path": {"type": "string", "description": "URL de YouTube/multimedia o ruta a un archivo de audio local"}
            },
            "required": ["url_or_path"]
        }
    },
    # ── Voz Creativa & Estudio (Kokoro-82M) ───────────────────
    {
        "name": "voice_creative_generate",
        "description": "Genera audio de voz con alta expresividad, entonación humana natural y variedad de timbres vocales usando Kokoro-82M en CPU.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto a sintetizar en voz de alta fidelidad"},
                "voice": {"type": "string", "description": "ID de la voz (ej: 'em_santa', 'bm_george', 'ef_dora', 'af_bella', 'am_adam')", "default": "em_santa"},
                "speed": {"type": "number", "description": "Velocidad de locución (ej: 0.9, 1.0, 1.1)", "default": 1.0}
            },
            "required": ["text"]
        }
    },
    {
        "name": "voice_speak_notification",
        "description": "Emite una notificación hablada por los altavoces de la PC con voz británica ('bm_george') o española ('em_santa') y aviso visual en el teclado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Mensaje a pronunciar por altavoces"},
                "voice": {"type": "string", "enum": ["bm_george", "em_santa", "am_adam", "ef_dora"], "description": "Voz de locución", "default": "bm_george"},
                "visual_style": {"type": "string", "description": "Estilo de animación del teclado (ej: 'synthwave', 'cyberpunk', 'police')", "default": "synthwave"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "voice_creative_list",
        "description": "Lista el catálogo de voces expresivas disponibles (español, inglés americano/británico).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    # ── Generación de Imagen (Diffusers / ComfyUI) ───────────
    {
        "name": "image_ai_generate",
        "description": "Genera una imagen con IA a partir de una descripción textual mediante difusión local en CPU / Shared Memory o ComfyUI.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {"type": "string", "description": "Descripción detallada de la imagen a generar"},
                "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"], "description": "Relación de aspecto", "default": "1:1"}
            },
            "required": ["prompt"]
        }
    }
]

# ── Handlers ───────────────────────────────────────────────


def _kasa_resolve_device(name: str):
    """Resolve device name to (name, ip)."""
    key = name.lower().strip()
    if key in KASA_DEVICES:
        return key, KASA_DEVICES[key]
    if key in KASA_ALIASES and KASA_ALIASES[key] in KASA_DEVICES:
        target = KASA_ALIASES[key]
        return target, KASA_DEVICES[target]
    return None, None


async def _kasa_set_plug_state(device_name: str, turn_on: bool) -> str:
    """Set plug state via Kasa protocol."""
    from kasa import SmartPlug

    if device_name.lower() in ["todo", "todos", "all"]:
        results = []
        for dev_name, dev_ip in KASA_DEVICES.items():
            plug = SmartPlug(dev_ip)
            await plug.update()
            if turn_on:
                await plug.turn_on()
                results.append(f"{dev_name}: ON")
            else:
                await plug.turn_off()
                results.append(f"{dev_name}: OFF")
        return "Dispositivos actualizados: " + ", ".join(results)

    target, ip = _kasa_resolve_device(device_name)
    if not ip:
        return f"Dispositivo '{device_name}' no reconocido. Disponibles: ElektroDante, Lux, todos."

    plug = SmartPlug(ip)
    await plug.update()
    if turn_on:
        await plug.turn_on()
        return f"'{target}' encendido correctamente."
    else:
        await plug.turn_off()
        return f"'{target}' apagado correctamente."


async def _kasa_get_plugs_status() -> str:
    """Get status of all plugs."""
    from kasa import SmartPlug

    status_list = []
    for name, ip in KASA_DEVICES.items():
        plug = SmartPlug(ip)
        await plug.update()
        state_str = "Encendido" if plug.is_on else "Apagado"
        status_list.append(f"{name.capitalize()} ({ip}): {state_str}")
    return "\n".join(status_list)


def _kasa_set_plug_state_handler(args):
    device_name = args.get("device_name", "")
    turn_on = args.get("turn_on", False)
    try:
        return asyncio.run(_kasa_set_plug_state(device_name, turn_on))
    except Exception as e:
        return f"Error controlando enchufe: {e}"


def _kasa_get_plugs_status_handler(args):
    try:
        return asyncio.run(_kasa_get_plugs_status())
    except Exception as e:
        return f"Error obteniendo estado: {e}"


def _control_keyboard_backlight(args):
    level = args.get("level", "off")
    lvl = level.lower().strip()
    if lvl not in ["off", "low", "med", "high"]:
        lvl = "off"
    try:
        if shutil.which("asusctl"):
            res = subprocess.run(["asusctl", "leds", "set", lvl], capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return f"Luz del teclado configurada en: {lvl.upper()}"
            return f"Error asusctl: {res.stderr.strip()}"
        return "asusctl no encontrado en el sistema."
    except Exception as e:
        return f"Error al cambiar brillo del teclado: {e}"


def _trigger_visual_alert(args):
    level = args.get("level", "normal")
    duration = args.get("duration")
    style = args.get("style")
    colors = args.get("colors")
    speed_ms = args.get("speed_ms")
    include_lamp = args.get("include_lamp", False)
    try:
        from visual_notifier import notifier
        if style or colors:
            return notifier.animate(style=style, colors=colors, duration=duration, speed_ms=speed_ms, include_lamp=include_lamp)
        return notifier.animate(level=level, duration=duration, speed_ms=speed_ms, include_lamp=include_lamp)
    except Exception as e:
        return f"Error activando alerta visual: {e}"


def _execute_sleep_routine(args):
    shutdown_pc = args.get("shutdown_pc", False)
    from kasa import SmartPlug

    actions_done = []

    async def _run_kasa_sleep():
        try:
            lux = SmartPlug(KASA_DEVICES["lux"])
            await lux.update()
            await lux.turn_off()
            actions_done.append("Lux (Luz de habitación): Apagada")
        except Exception as e:
            actions_done.append(f"Error Lux: {e}")

        try:
            ed = SmartPlug(KASA_DEVICES["elektrodante"])
            await ed.update()
            await ed.turn_on()
            actions_done.append("ElektroDante (Carga nocturna): Encendido")
        except Exception as e:
            actions_done.append(f"Error ElektroDante: {e}")

    try:
        asyncio.run(_run_kasa_sleep())
    except Exception as e:
        actions_done.append(f"Error general Kasa: {e}")

    if not shutdown_pc:
        _control_keyboard_backlight({"level": "off"})
        actions_done.append("Luz del Teclado: Apagada al mínimo (0)")
        actions_done.append("Computadora: Permanece encendida")
        return "Rutina de Dormir Ejecutada:\n" + "\n".join(f"- {a}" for a in actions_done) + "\n\n¡Que descanses!"
    else:
        actions_done.append("Computadora: Apagando sistema en 3 segundos...")
        subprocess.Popen(["shutdown", "-h", "now"])
        return "Rutina de Despedida:\n" + "\n".join(f"- {a}" for a in actions_done) + "\n\nHasta mañana."


def _dev_system_telemetry(args):
    try:
        from dev_controller import dev_controller
        return dev_controller.get_system_telemetry()
    except Exception as e:
        return f"Error en telemetria dev: {e}"


def _dev_service_control(args):
    service_name = args.get("service_name", "")
    action = args.get("action", "status")
    try:
        from dev_controller import dev_controller
        return dev_controller.manage_service(service_name, action)
    except Exception as e:
        return f"Error gestionando servicio {service_name}: {e}"


def _dev_process_monitor(args):
    count = args.get("count", 5)
    try:
        from dev_controller import dev_controller
        return dev_controller.get_top_processes(count)
    except Exception as e:
        return f"Error monitoreando procesos: {e}"


def _dev_git_quick_action(args):
    repo_path_or_name = args.get("repo_path_or_name", "")
    git_command = args.get("git_command", "status")
    try:
        from dev_controller import dev_controller
        return dev_controller.git_repo_action(repo_path_or_name, git_command)
    except Exception as e:
        return f"Error en accion git: {e}"


def _audit_git_repositories(args):
    base_dir = args.get("base_dir", "/media/darkseid/DATA/Repos")
    try:
        from git_repository_auditor import GitRepositoryAuditor
        auditor = GitRepositoryAuditor(base_dir=Path(base_dir))
        return auditor.generate_report(max_items=25)
    except Exception as e:
        return f"Error auditando repositorios: {e}"


def _github_monitor_status(args):
    try:
        db_path = os.path.expanduser("~/.local/share/ai-lab/github_monitor.db")
        if not os.path.exists(db_path):
            return "El monitor de GitHub no ha generado base de datos aun. Asegurate de que github-monitor.service este activo."
        
        import sqlite3
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row

        watched_count = conn.execute("SELECT COUNT(*) as c FROM watched_repos WHERE is_active = 1").fetchone()["c"]
        commits_count = conn.execute("SELECT COUNT(*) as c FROM seen_commits").fetchone()["c"]
        runs_count = conn.execute("SELECT COUNT(*) as c FROM seen_workflow_runs").fetchone()["c"]
        notifs_count = conn.execute("SELECT COUNT(*) as c FROM notification_history").fetchone()["c"]

        recent_alerts = conn.execute("""
        SELECT timestamp, event_type, repo_name, title, message, urgency
        FROM notification_history
        ORDER BY id DESC LIMIT 5
        """).fetchall()

        watched_list = conn.execute("SELECT repo_name, added_at, last_polled FROM watched_repos WHERE is_active = 1").fetchall()
        conn.close()

        lines = [
            "Estado de Telemetria - GitHub Activity & Actions Monitor",
            f"* Repositorios Monitoreados: `{watched_count}`",
            f"* Commits Rastreados: `{commits_count}`",
            f"* Workflows Evaluados: `{runs_count}`",
            f"* Alertas Emitidas: `{notifs_count}`\n",
            "Repositorios Activos:"
        ]
        for r in watched_list:
            last = r["last_polled"] or "Pendiente de polling"
            lines.append(f"  - `{r['repo_name']}` (Ultimo check: {last})")

        if recent_alerts:
            lines.append("\nUltimas Alertas Enviadas al Escritorio:")
            for a in recent_alerts:
                lines.append(f"  - [{a['urgency'].upper()}] `{a['repo_name']}` - *{a['title']}* ({a['timestamp']})")

        return "\n".join(lines)
    except Exception as e:
        return f"Error consultando monitor de GitHub: {e}"


def _github_watch_repo(args):
    repo_name = args.get("repo_name", "")
    clean_repo = repo_name.strip()
    if "/" not in clean_repo:
        return f"Error: '{clean_repo}' no es valido. Debe tener formato 'propietario/repo' (ej: 'dantecc10/ai-lab')."
    
    try:
        from scripts.tools.github_monitor import GitHubMonitor
        monitor = GitHubMonitor()
        added = monitor.add_watched_repo(clean_repo)
        if added:
            return f"Repositorio `{clean_repo}` agregado al monitoreo permanente de GitHub."
        else:
            return f"El repositorio `{clean_repo}` ya estaba en la lista de monitoreo."
    except Exception as e:
        return f"Error agregando repositorio a monitoreo: {e}"


def _github_unwatch_repo(args):
    repo_name = args.get("repo_name", "")
    clean_repo = repo_name.strip()
    try:
        from scripts.tools.github_monitor import GitHubMonitor
        monitor = GitHubMonitor()
        removed = monitor.remove_watched_repo(clean_repo)
        if removed:
            return f"Repositorio `{clean_repo}` desactivado del monitoreo permanente."
        else:
            return f"El repositorio `{clean_repo}` no estaba activo en el monitoreo."
    except Exception as e:
        return f"Error desactivando repositorio: {e}"


def _github_actions_status(args):
    repo_name = args.get("repo_name", "dantecc10/ai-lab")
    clean_repo = repo_name.strip() if repo_name else "dantecc10/ai-lab"
    try:
        res = subprocess.run(
            ["gh", "run", "list", "-R", clean_repo, "-L", "5"],
            capture_output=True, text=True, timeout=10
        )
        if res.returncode == 0 and res.stdout.strip():
            return f"GitHub Actions Runs (`{clean_repo}`):\n\n```\n{res.stdout.strip()}\n```"
        elif res.stderr:
            return f"Error consultando Actions: {res.stderr.strip()}"
        return f"No se encontraron ejecuciones de workflows para `{clean_repo}`."
    except Exception as e:
        return f"Error ejecutando gh run list: {e}"


def _media_download_url(args):
    url = args.get("url", "")
    media_type = args.get("media_type", "audio")
    try:
        from media_processor import media_processor
        res = media_processor.download_media(url, media_type=media_type)
        return f"Descarga lista: '{res['title']}' ({res['media_type'].upper()}, {res['file_size_mb']}MB) en: {res['file_path']}"
    except Exception as e:
        return f"Error descargando multimedia: {e}"


def _media_transcribe_audio(args):
    url_or_path = args.get("url_or_path", "")
    try:
        from media_processor import media_processor
        res = media_processor.process_and_transcribe(url_or_path)
        return f"Transcripcion Whisper de '{res['title']}' ({res['word_count']} palabras):\n\n{res['text'][:3500]}"
    except Exception as e:
        return f"Error transcribiendo audio con Whisper: {e}"


def _media_summarize_content(args):
    url_or_path = args.get("url_or_path", "")
    try:
        from media_processor import media_processor
        res = media_processor.summarize_video_or_audio(url_or_path)
        return res.get("summary") or "Sin resumen disponible."
    except Exception as e:
        return f"Error resumiendo contenido con Whisper y Gemma 4: {e}"


def _voice_creative_generate(args):
    text = args.get("text", "")
    voice = args.get("voice", "em_santa")
    speed = args.get("speed", 1.0)
    try:
        from creative_voice_engine import creative_voice_engine
        res = creative_voice_engine.synthesize(text, voice=voice, speed=float(speed), output_format="ogg")
        return f"Audio de alta fidelidad generado: '{res['voice_name']}' ({res['style']}, {res['duration_sec']}s) en: {res['file_path']}"
    except Exception as e:
        return f"Error generando voz creativa: {e}"


def _voice_speak_notification(args):
    message = args.get("message", "")
    voice = args.get("voice", "bm_george")
    visual_style = args.get("visual_style", "synthwave")
    try:
        from creative_voice_engine import creative_voice_engine
        res = creative_voice_engine.speak_notification(
            message=message,
            voice=voice,
            play_local=True,
            visual_style=visual_style
        )
        return f"Notificacion hablada emitida con voz '{res['voice_name']}': '{message}'"
    except Exception as e:
        return f"Error emitiendo notificacion hablada: {e}"


def _voice_creative_list(args):
    try:
        from creative_voice_engine import creative_voice_engine
        voices = creative_voice_engine.list_voices()
        lines = ["Catalogo de Voces de Alta Fidelidad (Kokoro-82M):"]
        for v in voices:
            lines.append(f"  - [{v['id']}] {v['name']} ({v['gender']} - {v['style']}): {v['desc']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error consultando voces: {e}"


def _image_ai_generate(args):
    prompt = args.get("prompt", "")
    aspect_ratio = args.get("aspect_ratio", "1:1")
    try:
        from image_generator import image_generator
        res = image_generator.generate_image(prompt=prompt, aspect_ratio=aspect_ratio)
        return f"Imagen generada ({res['width']}x{res['height']}, {res['gen_time_sec']}s): {res['file_path']}"
    except Exception as e:
        return f"Error generando imagen: {e}"


import shutil

HANDLERS = {
    "kasa_set_plug_state": _kasa_set_plug_state_handler,
    "kasa_get_plugs_status": _kasa_get_plugs_status_handler,
    "control_keyboard_backlight": _control_keyboard_backlight,
    "trigger_visual_alert": _trigger_visual_alert,
    "execute_sleep_routine": _execute_sleep_routine,
    "dev_system_telemetry": _dev_system_telemetry,
    "dev_service_control": _dev_service_control,
    "dev_process_monitor": _dev_process_monitor,
    "dev_git_quick_action": _dev_git_quick_action,
    "audit_git_repositories": _audit_git_repositories,
    "github_monitor_status": _github_monitor_status,
    "github_watch_repo": _github_watch_repo,
    "github_unwatch_repo": _github_unwatch_repo,
    "github_actions_status": _github_actions_status,
    "media_download_url": _media_download_url,
    "media_transcribe_audio": _media_transcribe_audio,
    "media_summarize_content": _media_summarize_content,
    "voice_creative_generate": _voice_creative_generate,
    "voice_speak_notification": _voice_speak_notification,
    "voice_creative_list": _voice_creative_list,
    "image_ai_generate": _image_ai_generate,
}
