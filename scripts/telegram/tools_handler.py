"""
AI Lab — Telegram Bot Tools & Function Calling Handler
Define herramientas locales seguras y endpoints para comandos de diagnóstico y función calling.
"""

import os
import sys
import json
import shutil
import subprocess
import psutil
import urllib.request
from pathlib import Path
from typing import Dict, Any, List

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


class ToolsHandler:
    """Manejador de herramientas del sistema y ejecución para el Bot de Telegram."""

    def __init__(self):
        pass

    def get_gpu_status(self) -> str:
        """Obtiene métricas detalladas de la GPU NVIDIA vía nvidia-smi."""
        if not shutil.which("nvidia-smi"):
            return "❌ `nvidia-smi` no está disponible en este sistema."

        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=name,driver_version,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
                "--format=csv,noheader,nounits"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode != 0:
                return f"⚠️ Error al ejecutar nvidia-smi: {res.stderr}"

            parts = [p.strip() for p in res.stdout.strip().split(",")]
            if len(parts) >= 7:
                name, driver, temp, util, mem_used, mem_tot, power = parts[:7]
                mem_used_f = float(mem_used)
                mem_tot_f = float(mem_tot)
                pct = (mem_used_f / mem_tot_f) * 100 if mem_tot_f > 0 else 0

                return (
                    f"🎮 *GPU NVIDIA Status*\n"
                    f"• **Modelo**: `{name}`\n"
                    f"• **Driver**: `{driver}`\n"
                    f"• **VRAM**: `{mem_used_f:.0f} MiB / {mem_tot_f:.0f} MiB` (*{pct:.1f}%*)\n"
                    f"• **Uso GPU**: `{util}%`\n"
                    f"• **Temperatura**: `{temp}°C`\n"
                    f"• **Consumo**: `{power} W`"
                )
            return f"```\n{res.stdout.strip()}\n```"
        except Exception as e:
            return f"⚠️ Error obteniendo estado de GPU: {e}"

    def get_system_status(self) -> str:
        """Comprueba el estado de los servicios de AI Lab y recursos de la máquina."""
        # Comprobar servicios
        services = {
            "Gemma 4 12B (GPU:9090)": "http://127.0.0.1:9090/v1/models",
            "Gemma 4 E4B (CPU:9091)": "http://127.0.0.1:9091/v1/models",
            "Whisper STT (:9093)": "http://127.0.0.1:9093/health",
            "ChatShare (:9095)": "http://127.0.0.1:9095/health"
        }

        status_lines = []
        for name, url in services.items():
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=2.0) as resp:
                    if resp.status == 200:
                        status_lines.append(f"🟢 **{name}**: *Activo*")
                    else:
                        status_lines.append(f"🟡 **{name}**: HTTP {resp.status}")
            except Exception:
                status_lines.append(f"🔴 **{name}**: *Inactivo / Offline*")

        # Recursos de sistema
        cpu_pct = psutil.cpu_percent(interval=0.1)
        mem = psutil.virtual_memory()
        swap = psutil.swap_memory()
        disk = psutil.disk_usage('/')

        info = (
            f"📊 *AI Lab & System Status*\n\n"
            f"**Servicios IA:**\n" + "\n".join(status_lines) + "\n\n"
            f"**Recursos de Hardware:**\n"
            f"• **CPU**: `{cpu_pct}%` ({psutil.cpu_count(logical=True)} hilos)\n"
            f"• **RAM**: `{mem.used / (1024**3):.1f} GB / {mem.total / (1024**3):.1f} GB` (*{mem.percent}%*)\n"
            f"• **Swap**: `{swap.used / (1024**3):.1f} GB / {swap.total / (1024**3):.1f} GB` (*{swap.percent}%*)\n"
            f"• **Disco (/)**: `{disk.used / (1024**3):.1f} GB / {disk.total / (1024**3):.1f} GB` (*{disk.percent}%*)"
        )
        return info

    def run_safe_command(self, cmd_str: str) -> str:
        """Ejecuta un comando de terminal de forma segura con timeout."""
        # Comprobación básica de comandos peligrosos
        dangerous = ["rm -rf /", "mkfs", ":(){ :|:& };:", "dd if=/dev/zero", "> /dev/sda"]
        for d in dangerous:
            if d in cmd_str:
                return f"🛑 *Comando bloqueado por seguridad:* `{cmd_str}`"

        try:
            res = subprocess.run(
                cmd_str,
                shell=True,
                capture_output=True,
                text=True,
                timeout=25,
                cwd=str(Path.home())
            )
            out = (res.stdout or "").strip()
            err = (res.stderr or "").strip()

            combined = ""
            if out:
                combined += out
            if err:
                combined += f"\n[stderr]:\n{err}" if combined else err

            if not combined:
                combined = "(Comando completado sin salida)"

            if len(combined) > 3500:
                combined = combined[:3500] + "\n... [Salida truncada]"

            return f"```bash\n$ {cmd_str}\n{combined}\n```"
        except subprocess.TimeoutExpired:
            return f"⏱️ *El comando excedió el tiempo límite (25s):* `{cmd_str}`"
        except Exception as e:
            return f"⚠️ Error al ejecutar comando: {e}"

    def search_web(self, query: str) -> str:
        """Busca información actualizada en DuckDuckGo."""
        try:
            from duckduckgo_search import DDGS
            with DDGS() as ddgs:
                results = list(ddgs.text(query, max_results=4))
                if not results:
                    return "No se encontraron resultados para la búsqueda."
                formatted = []
                for r in results:
                    formatted.append(f"• **{r.get('title')}**\n  {r.get('body')}\n  🔗 {r.get('href')}")
                return "\n\n".join(formatted)
        except Exception as e:
            return f"⚠️ Error al buscar en la web: {e}"

    def send_email(self, to_email: str, subject: str, body: str) -> str:
        """Envía un correo electrónico utilizando el servidor SMTP propio/local (100% gratis vía msmtp)."""
        if not to_email or "@" not in to_email:
            return "❌ Dirección de correo inválida."
        try:
            email_content = f"To: {to_email}\nSubject: {subject}\nContent-Type: text/plain; charset=UTF-8\n\n{body}"
            # Intentar con msmtp
            if shutil.which("msmtp"):
                proc = subprocess.run(
                    ["msmtp", "-a", "default", to_email],
                    input=email_content,
                    text=True,
                    capture_output=True,
                    timeout=15
                )
                if proc.returncode == 0:
                    return f"📧 Correo enviado exitosamente a `{to_email}` con asunto: *{subject}*"
                else:
                    return f"⚠️ Error msmtp: {proc.stderr.strip()}"
            
            # Fallback smtplib directo
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = "ai-lab@castelancarpinteyro.com"
            msg["To"] = to_email
            with smtplib.SMTP("mail.castelancarpinteyro.com", 587, timeout=15) as server:
                server.starttls()
                server.login("ai-lab@castelancarpinteyro.com", "26IAmailsender!!")
                server.send_message(msg)
            return f"📧 Correo enviado exitosamente a `{to_email}` con asunto: *{subject}*"
        except Exception as e:
            return f"⚠️ Error al enviar correo: {e}"

    def trigger_visual_alert(
        self,
        level: str = "normal",
        duration: float = None,
        style: str = None,
        colors: list = None,
        speed_ms: int = None,
        include_lamp: bool = False
    ) -> str:
        """Reproduce una secuencia dinámica de luces en el teclado ASUS y lámpara Lux."""
        try:
            from scripts.tools.visual_notifier import notifier
            if style or colors:
                return notifier.animate(style=style, colors=colors, duration=duration, speed_ms=speed_ms, include_lamp=include_lamp)
            return notifier.animate(level=level, duration=duration, speed_ms=speed_ms, include_lamp=include_lamp)
        except Exception as e:
            return f"⚠️ Error reproduciendo secuencia visual: {e}"

    def send_desktop_notification(self, title: str, message: str, priority: str = "normal") -> str:
        """Envía una notificación emergente en Pop!_OS vía notify-send y reproduce secuencia de luces en teclado."""
        try:
            subprocess.run(["notify-send", "-a", "AI Lab Assistant", "-i", "dialog-information", title, message], check=False, timeout=5)
            # Reproducir secuencia visual acorde a la prioridad (normal 1-3s, important 3-6s, critical 6-10s)
            self.trigger_visual_alert(level=priority, include_lamp=True)
            return f"🔔 Notificación de escritorio enviada con aviso visual ({priority.upper()}): *{title}*"
        except Exception as e:
            return f"⚠️ Error al enviar notificación: {e}"

    def send_webhook_message(self, webhook_url: str, message: str) -> str:
        """Envía un mensaje a un Webhook gratuito (Discord, Slack, etc.)."""
        try:
            req = urllib.request.Request(
                webhook_url,
                data=json.dumps({"content": message, "text": message}).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status in (200, 204):
                    return "✅ Mensaje enviado exitosamente al webhook."
                return f"⚠️ Webhook respondió con código HTTP {resp.status}"
        except Exception as e:
            return f"⚠️ Error al enviar a webhook: {e}"

    def create_whatsapp_link(self, phone: str, message: str) -> str:
        """Genera un enlace directo gratuito para enviar mensajes por WhatsApp Web (sin API de pago)."""
        import urllib.parse
        clean_phone = "".join(filter(str.isdigit, phone))
        encoded_msg = urllib.parse.quote(message)
        link = f"https://wa.me/{clean_phone}?text={encoded_msg}"
        return f"📱 *Enlace directo de WhatsApp:*\n{link}\n\n*(Haz clic para abrir WhatsApp y enviar el mensaje directamente)*"

    # ── Recordatorios y Temporizadores ────────────────────────
    def add_reminder(self, title: str, due: str, priority: str = "normal", category: str = "general") -> str:
        """Crea un recordatorio o temporizador omnicanal."""
        try:
            from scripts.tools.reminder_engine import reminder_engine
            res = reminder_engine.add_reminder(title=title, due=due, priority=priority, category=category)
            return f"⏰ *Recordatorio programado exitosamente:*\n• **ID:** `#{res['id']}`\n• **Título:** *{res['title']}*\n• **Vence en:** `{res['time_left']}` ({res['due_at']})\n• **Prioridad:** `{res['priority'].upper()}`"
        except Exception as e:
            return f"⚠️ Error programando recordatorio: {e}"

    def list_reminders(self) -> str:
        """Lista recordatorios pendientes."""
        try:
            from scripts.tools.reminder_engine import reminder_engine
            items = reminder_engine.list_pending_reminders()
            if not items:
                return "ℹ️ No tienes recordatorios ni temporizadores pendientes."
            lines = [f"📋 *Recordatorios y Temporizadores Pendientes ({len(items)}):*\n"]
            for i in items:
                lines.append(f"• `[#{i['id']}]` *{i['title']}* ➔ Vence en `{i['time_left']}` ({i['due_at']}) `[{i['priority'].upper()}]`")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ Error consultando recordatorios: {e}"

    def cancel_reminder(self, reminder_id: int) -> str:
        """Cancela un recordatorio por ID."""
        try:
            from scripts.tools.reminder_engine import reminder_engine
            ok = reminder_engine.cancel_reminder(reminder_id)
            if ok:
                return f"✅ Recordatorio `#{reminder_id}` cancelado y eliminado."
            return f"ℹ️ No se encontró el recordatorio `#{reminder_id}`."
        except Exception as e:
            return f"⚠️ Error cancelando recordatorio: {e}"

    # ── Dev Ops & Control Remoto ─────────────────────────────
    def get_dev_telemetry(self) -> str:
        """Dashboard de telemetría dev en tiempo real (GPU, CPU, RAM, Disco, Servicios)."""
        try:
            from scripts.tools.dev_controller import dev_controller
            return dev_controller.get_system_telemetry()
        except Exception as e:
            return f"⚠️ Error obteniendo telemetría dev: {e}"

    def manage_dev_service(self, service_name: str, action: str = "status") -> str:
        """Gestiona un servicio systemd (start, stop, restart, status, logs)."""
        try:
            from scripts.tools.dev_controller import dev_controller
            return dev_controller.manage_service(service_name, action)
        except Exception as e:
            return f"⚠️ Error gestionando servicio: {e}"

    def get_top_processes(self, count: int = 5) -> str:
        """Muestra los procesos principales en CPU y RAM."""
        try:
            from scripts.tools.dev_controller import dev_controller
            return dev_controller.get_top_processes(count)
        except Exception as e:
            return f"⚠️ Error obteniendo procesos: {e}"

    def git_repo_action(self, repo_path_or_name: str, git_command: str = "status") -> str:
        """Ejecuta una acción git en un repositorio del acervo en /media/darkseid/DATA/Repos."""
        try:
            from scripts.tools.dev_controller import dev_controller
            return dev_controller.git_repo_action(repo_path_or_name, git_command)
        except Exception as e:
            return f"⚠️ Error en acción git: {e}"

    # ── Media, Audio & Video Processing (Whisper + yt-dlp) ────
    def download_media(self, url: str, media_type: str = "audio") -> str:
        """Descarga audio o video de YouTube u otra URL con yt-dlp."""
        try:
            from scripts.tools.media_processor import media_processor
            res = media_processor.download_media(url, media_type=media_type)
            return (
                f"📥 **Descarga Completada con yt-dlp:**\n"
                f"• **Título:** *{res['title']}*\n"
                f"• **Canal:** `{res['uploader']}`\n"
                f"• **Tipo:** `{res['media_type'].upper()}` ({res['file_size_mb']} MB)\n"
                f"• **Ruta Local:** `{res['file_path']}`"
            )
        except Exception as e:
            return f"⚠️ Error descargando multimedia: {e}"

    def transcribe_media(self, url_or_path: str) -> str:
        """Transcribe audio local o video de YouTube con Whisper STT (:9093)."""
        try:
            from scripts.tools.media_processor import media_processor
            res = media_processor.process_and_transcribe(url_or_path)
            return (
                f"🎙️ **Transcripción Whisper STT Completada:**\n"
                f"• **Título:** *{res['title']}* (`{res['word_count']}` palabras)\n"
                f"• **Archivo TXT:** `{res['transcript_path']}`\n\n"
                f"📝 **Texto Extraído:**\n{res['text'][:3500]}"
            )
        except Exception as e:
            return f"⚠️ Error en transcripción Whisper: {e}"

    def summarize_media(self, url_or_path: str) -> str:
        """Descarga, transcribe con Whisper y genera resumen inteligente con Gemma 4."""
        try:
            from scripts.tools.media_processor import media_processor
            res = media_processor.summarize_video_or_audio(url_or_path)
            return res.get("summary") or "Resumen no generado."
        except Exception as e:
            return f"⚠️ Error resumiendo contenido multimedia: {e}"

    # ── Voz Creativa & Estudio (Kokoro-82M) ───────────────────
    def generate_creative_voice(self, text: str, voice: str = "em_santa", speed: float = 1.0) -> str:
        """Genera un archivo de audio con voz expresiva y entonación de estudio."""
        try:
            from scripts.voice.creative_voice_engine import creative_voice_engine
            res = creative_voice_engine.synthesize(text, voice=voice, speed=speed, output_format="ogg")
            return (
                f"🎙️ **Voz de Alta Fidelidad Generada:**\n"
                f"• **Voz:** *{res['voice_name']}* ({res['style']})\n"
                f"• **Duración:** `{res['duration_sec']}s` (renderizado en `{res['gen_time_sec']}s` en CPU)\n"
                f"• **Archivo:** `{res['file_path']}`"
            )
        except Exception as e:
            return f"⚠️ Error generando voz creativa: {e}"

    def speak_notification(self, message: str, voice: str = "bm_george", visual_style: str = "synthwave") -> str:
        """Sintetiza un anuncio por voz (inglés bm_george o español em_santa) y lo reproduce localmente con aviso visual."""
        try:
            from scripts.voice.creative_voice_engine import creative_voice_engine
            res = creative_voice_engine.speak_notification(
                message=message,
                voice=voice,
                play_local=True,
                visual_style=visual_style
            )
            return f"🔊 **Notificación Hablada Emitida:**\n• **Voz:** *{res['voice_name']}* ({res['style']})\n• **Mensaje:** *\"{message}\"*\n• **Aviso Visual:** `{visual_style.upper()}`"
        except Exception as e:
            return f"⚠️ Error emitiendo notificación hablada: {e}"

    def list_creative_voices(self) -> str:
        """Lista el catálogo de voces de alta fidelidad disponibles."""
        try:
            from scripts.voice.creative_voice_engine import creative_voice_engine
            voices = creative_voice_engine.list_voices()
            lines = ["🎭 **Catálogo de Voces de Alta Fidelidad (Kokoro-82M):**\n"]
            for v in voices:
                lines.append(f"• `{v['id']}`: **{v['name']}** ({v['gender']} - {v['style']})\n  _{v['desc']}_")
            return "\n".join(lines)
        except Exception as e:
            return f"⚠️ Error consultando catálogo de voces: {e}"

    # ── Generación de Imagen (Diffusers / ComfyUI) ───────────
    def generate_ai_image(self, prompt: str, aspect_ratio: str = "1:1") -> str:
        """Genera una imagen con IA por difusión a partir de un prompt."""
        try:
            from scripts.tools.image_generator import image_generator
            res = image_generator.generate_image(prompt=prompt, aspect_ratio=aspect_ratio)
            return (
                f"🎨 **Imagen Generada Exitosamente:**\n"
                f"• **Prompt:** *{res['prompt']}*\n"
                f"• **Dimensiones:** `{res['width']}x{res['height']}` ({res['aspect_ratio']})\n"
                f"• **Tiempo de render:** `{res['gen_time_sec']}s` (CPU/Shared)\n"
                f"• **Ruta:** `{res['file_path']}`"
            )
        except Exception as e:
            return f"⚠️ Error generando imagen: {e}"

    def control_keyboard_backlight(self, level: str = "off") -> str:
        """Controla el brillo del teclado ASUS (off, low, med, high)."""
        lvl = level.lower().strip()
        if lvl not in ["off", "low", "med", "high"]:
            lvl = "off"
        try:
            if shutil.which("asusctl"):
                res = subprocess.run(["asusctl", "leds", "set", lvl], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    return f"💡 Luz del teclado configurada en: *{lvl.upper()}*"
                return f"⚠️ Error asusctl: {res.stderr.strip()}"
            return "❌ asusctl no encontrado en el sistema."
        except Exception as e:
            return f"⚠️ Error al cambiar brillo del teclado: {e}"

    def control_kasa_plug(self, device_name: str, state: str) -> str:
        """Controla enchufes inteligentes Kasa (Lux, ElektroDante, todos)."""
        import asyncio
        from kasa import Discover
        turn_on = state.lower() in ["on", "encender", "encendido", "true", "1"]
        known_ips = {
            "elektrodante": "192.168.1.70",
            "lux": "192.168.1.71"
        }
        aliases = {"luz": "lux", "foco": "lux", "electro": "elektrodante", "escritorio": "elektrodante"}

        async def _kasa_run():
            target = device_name.lower().strip()
            target_key = aliases.get(target, target)
            results = []

            # Intentar conexión directa
            if target_key in ["todo", "todos", "all"]:
                for name, ip in known_ips.items():
                    try:
                        plug = await Discover.discover_single(ip)
                        await plug.update()
                        if turn_on:
                            await plug.turn_on()
                            results.append(f"{plug.alias}: Encendido (ON)")
                        else:
                            await plug.turn_off()
                            results.append(f"{plug.alias}: Apagado (OFF)")
                    except Exception:
                        pass
            elif target_key in known_ips:
                try:
                    plug = await Discover.discover_single(known_ips[target_key])
                    await plug.update()
                    if turn_on:
                        await plug.turn_on()
                        results.append(f"{plug.alias}: Encendido (ON)")
                    else:
                        await plug.turn_off()
                        results.append(f"{plug.alias}: Apagado (OFF)")
                except Exception:
                    pass

            # Si falló la conexión directa, recurrir a descubrimiento completo
            if not results:
                devs = await Discover.discover()
                for ip, d in devs.items():
                    alias = d.alias.lower().strip()
                    if target_key in ["todo", "todos", "all"] or target_key in alias:
                        if turn_on:
                            await d.turn_on()
                            results.append(f"{d.alias}: Encendido (ON)")
                        else:
                            await d.turn_off()
                            results.append(f"{d.alias}: Apagado (OFF)")

            if not results:
                return f"❌ No se pudo conectar al enchufe Kasa '{device_name}'."
            return "🔌 " + ", ".join(results)

        try:
            return asyncio.run(_kasa_run())
        except Exception as e:
            return f"⚠️ Error comunicándose con Kasa: {e}"

    def execute_sleep_routine(self, shutdown_pc: bool = False) -> str:
        """
        Ejecuta la rutina nocturna:
        - Lux (Luz): APAGAR
        - ElektroDante (Carga nocturna): ENCENDER / MANTENER ENCENDIDO
        - Si shutdown_pc es False: Apagar luz del teclado (asusctl leds set off)
        - Si shutdown_pc es True: Programar apagado del equipo (shutdown now)
        """
        import asyncio
        import threading
        import time
        from kasa import Discover
        
        actions_done = []

        # 1. Gestionar enchufes Kasa directamente por IP (rápido y fiable)
        async def _run_kasa_sleep():
            # Lux
            try:
                lux = await Discover.discover_single("192.168.1.71")
                await lux.update()
                await lux.turn_off()
                actions_done.append("🌑 **Lux (Luz de habitación):** *Apagada*")
            except Exception as e:
                actions_done.append(f"⚠️ Error Lux: {e}")

            # ElektroDante
            try:
                ed = await Discover.discover_single("192.168.1.70")
                await ed.update()
                await ed.turn_on()
                actions_done.append("⚡ **ElektroDante (Carga nocturna):** *Encendido*")
            except Exception as e:
                actions_done.append(f"⚠️ Error ElektroDante: {e}")

        try:
            asyncio.run(_run_kasa_sleep())
        except Exception as e:
            actions_done.append(f"⚠️ Error general Kasa: {e}")

        # 2. Gestionar teclado o apagado
        if not shutdown_pc:
            self.control_keyboard_backlight("off")
            actions_done.append("⌨️ **Luz del Teclado:** *Apagada al mínimo (oscuridad total)*")
            actions_done.append("💻 **Computadora:** *Permanece encendida*")
            report = (
                "🌙 **Rutina de Dormir Ejecutada:**\n\n" +
                "\n".join(f"• {a}" for a in actions_done) +
                "\n\n😴 ¡Que descanses! La habitación está a oscuras y tus dispositivos cargando."
            )
            return report
        else:
            actions_done.append("🛑 **Computadora:** *Apagando el sistema (shutdown 0)...*")
            report = (
                "👋 **Rutina de Despedida y Buenas Noches:**\n\n" +
                "\n".join(f"• {a}" for a in actions_done) +
                "\n\n💤 Hasta mañana. Apagando equipo en 3 segundos..."
            )
            def _delayed_shutdown():
                time.sleep(3)
                subprocess.run("shutdown -h now", shell=True)

            threading.Thread(target=_delayed_shutdown, daemon=True).start()
            return report

    def audit_git_repositories(self, base_dir: str = "/media/darkseid/DATA/Repos") -> str:
        """Audita el estado de todos los repositorios Git en el acervo técnico."""
        try:
            from scripts.tools.git_repository_auditor import GitRepositoryAuditor
            auditor = GitRepositoryAuditor(base_dir=Path(base_dir))
            return auditor.generate_report(max_items=20)
        except Exception as e:
            return f"⚠️ Error auditando repositorios: {e}"

    def get_openai_tools_definition(self) -> List[Dict[str, Any]]:
        """Retorna las herramientas registradas en formato OpenAI function calling."""
        return [
            {
                "type": "function",
                "function": {
                    "name": "execute_sleep_routine",
                    "description": "Ejecuta la rutina nocturna de dormir: Apaga la luz Lux, deja encendido ElektroDante para cargar dispositivos en la noche, y apaga la luz del teclado (o apaga la computadora entera si se le solicita).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "shutdown_pc": {
                                "type": "boolean",
                                "description": "True si el usuario se despide para apagar la computadora (ej. 'Adiós, nos vemos mañana', 'Vámonos a dormir'). False si solo es hora de dormir manteniendo la compu encendida (ej. 'Es hora de dormir')."
                            }
                        },
                        "required": ["shutdown_pc"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_kasa_plug",
                    "description": "Enciende o apaga enchufes inteligentes Kasa (Lux, ElektroDante, todos).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "device_name": {"type": "string", "description": "Nombre del enchufe ('Lux', 'ElektroDante', 'todos')"},
                            "state": {"type": "string", "enum": ["on", "off"], "description": "'on' para encender, 'off' para apagar"}
                        },
                        "required": ["device_name", "state"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "control_keyboard_backlight",
                    "description": "Controla el brillo de la luz del teclado ASUS ROG/TUF ('off', 'low', 'med', 'high'). Útil para apagar la luz del teclado al dormir.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "level": {"type": "string", "enum": ["off", "low", "med", "high"], "description": "Nivel de brillo ('off', 'low', 'med', 'high')"}
                        },
                        "required": ["level"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_gpu_status",
                    "description": "Obtiene el estado de la GPU NVIDIA (VRAM usada, temperatura, consumo, uso de GPU).",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_system_status",
                    "description": "Obtiene el estado de los servicios locales (Gemma 4, Whisper, ChatShare) y hardware (CPU, RAM, Swap, Disco).",
                    "parameters": {"type": "object", "properties": {}, "required": []}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_email",
                    "description": "Envía un correo electrónico real utilizando el servidor SMTP propio (gratis).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "to_email": {"type": "string", "description": "Destinatario del correo"},
                            "subject": {"type": "string", "description": "Asunto del correo"},
                            "body": {"type": "string", "description": "Cuerpo del mensaje"}
                        },
                        "required": ["to_email", "subject", "body"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "send_desktop_notification",
                    "description": "Muestra una notificación en la pantalla del monitor del usuario vía notify-send.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Título de la notificación"},
                            "message": {"type": "string", "description": "Mensaje de la notificación"}
                        },
                        "required": ["title", "message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "create_whatsapp_link",
                    "description": "Genera un enlace gratuito de WhatsApp (wa.me) para enviar mensajes sin usar APIs de pago.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "phone": {"type": "string", "description": "Número telefónico con código de país (ej. 521234567890)"},
                            "message": {"type": "string", "description": "Texto a enviar"}
                        },
                        "required": ["phone", "message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "search_web",
                    "description": "Busca en la web información actualizada, noticias, clima o documentación.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "query": {"type": "string", "description": "Término de búsqueda"}
                        },
                        "required": ["query"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "trigger_visual_alert",
                    "description": "Control de efectos e iluminación libre del teclado ASUS ROG/TUF y lámpara: permite reproducir secuencias cromáticas personalizadas, estilos temáticos ('cyberpunk', 'police', 'matrix', 'rainbow', 'fire', 'aurora', 'heartbeat', 'synthwave', 'breathe', 'strobe'), listas de colores RGB arbitrarias, intervalos de velocidad personalizados y presets de notificación. Siempre retorna al color base Cian (#00ffff).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "style": {
                                "type": "string",
                                "enum": ["police", "cyberpunk", "synthwave", "matrix", "rainbow", "fire", "aurora", "heartbeat", "breathe", "strobe"],
                                "description": "Estilo temático de animación coreografiada (opcional)"
                            },
                            "colors": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Lista libre de colores hex o nombres (ej: ['ff0000', '00ffff', 'ff00ff'] o ['red', 'blue'])"
                            },
                            "level": {
                                "type": "string",
                                "enum": ["normal", "important", "critical", "error", "success", "warning"],
                                "description": "Preset de severidad/prioridad ('normal': 1-3s cian, 'important': 3-6s ámbar, 'critical': 6-10s rojo, 'success': verde)"
                            },
                            "duration": {
                                "type": "number",
                                "description": "Duración total en segundos (ej: 2.5, 5.0, 10.0)"
                            },
                            "speed_ms": {
                                "type": "integer",
                                "description": "Intervalo entre cambios de color/brillo en milisegundos (ej: 60ms para rápido, 200ms para lento)"
                            },
                            "include_lamp": {
                                "type": "boolean",
                                "description": "Si debe incluir parpadeo de la lámpara Lux (por defecto False en animaciones artísticas, True en alertas críticas)"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "audit_git_repositories",
                    "description": "Audita y revisa todos los repositorios de código en /media/darkseid/DATA/Repos para detectar cambios sin commitear, archivos nuevos o commits locales sin subir a GitHub/remoto.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "base_dir": {
                                "type": "string",
                                "description": "Directorio raíz de repositorios (por defecto '/media/darkseid/DATA/Repos')"
                            }
                        },
                        "required": []
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "run_shell_command",
                    "description": "Ejecuta un comando en la terminal Linux de la máquina local.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "command": {"type": "string", "description": "Comando bash a ejecutar"}
                        },
                        "required": ["command"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "add_reminder",
                    "description": "Programa un recordatorio o temporizador omnicanal (Telegram, escritorio, aviso visual en teclado).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string", "description": "Texto del recordatorio o tarea (ej: 'Revisar compilación', 'Sacar la pizza')"},
                            "due": {"type": "string", "description": "Tiempo natural o relativo (ej: '15m', '2h', '17:30', 'en 45 segundos')"},
                            "priority": {"type": "string", "enum": ["normal", "important", "critical"], "description": "Nivel de urgencia"}
                        },
                        "required": ["title", "due"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_reminders",
                    "description": "Lista todos los recordatorios y temporizadores pendientes.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "cancel_reminder",
                    "description": "Cancela un recordatorio por su ID numérico.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "reminder_id": {"type": "integer", "description": "ID del recordatorio a cancelar"}
                        },
                        "required": ["reminder_id"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_dev_telemetry",
                    "description": "Obtiene la telemetría en tiempo real del hardware: GPU VRAM/temperatura/potencia, RAM, Swap, Disco y estado de servicios IA.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "manage_dev_service",
                    "description": "Gestiona servicios systemd del entorno IA (start, stop, restart, status, logs).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "service_name": {"type": "string", "description": "Nombre del servicio (gemma4-server, e4b-server, whisper-server, telegram-bot, git-sentinel, chatmanager)"},
                            "action": {"type": "string", "enum": ["start", "stop", "restart", "status", "logs"], "description": "Acción a realizar"}
                        },
                        "required": ["service_name", "action"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "get_top_processes",
                    "description": "Consulta los procesos que más CPU y memoria RAM consumen actualmente en el sistema.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "count": {"type": "integer", "description": "Número de procesos a listar (por defecto 5)"}
                        }
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "git_repo_action",
                    "description": "Ejecuta comandos git (status, diff, log, branch, pull) en cualquier repositorio del acervo en /media/darkseid/DATA/Repos.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "repo_path_or_name": {"type": "string", "description": "Nombre de la carpeta o ruta del repositorio"},
                            "git_command": {"type": "string", "description": "Comando git (ej: 'status', 'log', 'diff', 'branch', 'pull')"}
                        },
                        "required": ["repo_path_or_name"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "download_media",
                    "description": "Descarga audio o video de YouTube, X, TikTok, Reddit o podcast mediante yt-dlp.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url": {"type": "string", "description": "URL del video/audio a descargar"},
                            "media_type": {"type": "string", "enum": ["audio", "video"], "description": "Tipo de descarga ('audio' mp3 o 'video' mp4)"}
                        },
                        "required": ["url"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "transcribe_media",
                    "description": "Transcribe la voz y el diálogo de un archivo local de audio/video o de una URL de YouTube usando Whisper STT (:9093).",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url_or_path": {"type": "string", "description": "URL de YouTube/multimedia o ruta a un archivo de audio local"}
                        },
                        "required": ["url_or_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "summarize_media",
                    "description": "Descarga, transcribe con Whisper y genera un resumen estructurado con Gemma 4 para un video de YouTube, podcast o audio.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "url_or_path": {"type": "string", "description": "URL de YouTube/multimedia o ruta a un archivo de audio"}
                        },
                        "required": ["url_or_path"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_creative_voice",
                    "description": "Genera un audio de voz de alta fidelidad, natural y expresiva usando el motor Kokoro-82M en CPU.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "text": {"type": "string", "description": "Texto a sintetizar en voz"},
                            "voice": {"type": "string", "description": "ID de la voz (ej: 'em_santa', 'bm_george', 'ef_dora', 'am_adam')", "default": "em_santa"},
                            "speed": {"type": "number", "description": "Velocidad de habla (ej: 0.9, 1.0, 1.1)", "default": 1.0}
                        },
                        "required": ["text"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "speak_notification",
                    "description": "Emite una notificación hablada por los altavoces de la PC con voz británica ('bm_george') o española ('em_santa') y aviso visual en el teclado.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "message": {"type": "string", "description": "Mensaje a pronunciar"},
                            "voice": {"type": "string", "enum": ["bm_george", "em_santa", "am_adam", "ef_dora"], "description": "Voz de locución", "default": "bm_george"},
                            "visual_style": {"type": "string", "description": "Estilo de animación del teclado (ej: 'synthwave', 'cyberpunk', 'police')", "default": "synthwave"}
                        },
                        "required": ["message"]
                    }
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "list_creative_voices",
                    "description": "Lista el catálogo de voces expresivas disponibles de alta fidelidad.",
                    "parameters": {"type": "object", "properties": {}}
                }
            },
            {
                "type": "function",
                "function": {
                    "name": "generate_ai_image",
                    "description": "Genera una imagen artística, realista o conceptual con IA mediante difusión local a partir de un prompt.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "prompt": {"type": "string", "description": "Descripción detallada de la imagen a generar en inglés o español"},
                            "aspect_ratio": {"type": "string", "enum": ["1:1", "16:9", "9:16", "4:3", "3:4"], "description": "Relación de aspecto", "default": "1:1"}
                        },
                        "required": ["prompt"]
                    }
                }
            }
        ]

    def execute_function_call(self, name: str, args: dict) -> str:
        """Ejecuta una llamada a función solicitada por el LLM."""
        if name == "generate_creative_voice":
            return self.generate_creative_voice(
                text=args.get("text", ""),
                voice=args.get("voice", "em_santa"),
                speed=args.get("speed", 1.0)
            )
        elif name == "speak_notification":
            return self.speak_notification(
                message=args.get("message", ""),
                voice=args.get("voice", "bm_george"),
                visual_style=args.get("visual_style", "synthwave")
            )
        elif name == "list_creative_voices":
            return self.list_creative_voices()
        elif name == "generate_ai_image":
            return self.generate_ai_image(
                prompt=args.get("prompt", ""),
                aspect_ratio=args.get("aspect_ratio", "1:1")
            )
        elif name == "trigger_visual_alert":
            return self.trigger_visual_alert(
                level=args.get("level", "normal"),
                duration=args.get("duration"),
                style=args.get("style"),
                colors=args.get("colors"),
                speed_ms=args.get("speed_ms"),
                include_lamp=args.get("include_lamp", False)
            )
        elif name == "add_reminder":
            return self.add_reminder(
                title=args.get("title", ""),
                due=args.get("due", "10m"),
                priority=args.get("priority", "normal")
            )
        elif name == "list_reminders":
            return self.list_reminders()
        elif name == "cancel_reminder":
            return self.cancel_reminder(args.get("reminder_id", 0))
        elif name == "get_dev_telemetry":
            return self.get_dev_telemetry()
        elif name == "manage_dev_service":
            return self.manage_dev_service(args.get("service_name", ""), args.get("action", "status"))
        elif name == "get_top_processes":
            return self.get_top_processes(args.get("count", 5))
        elif name == "git_repo_action":
            return self.git_repo_action(args.get("repo_path_or_name", ""), args.get("git_command", "status"))
        elif name == "download_media":
            return self.download_media(args.get("url", ""), args.get("media_type", "audio"))
        elif name == "transcribe_media":
            return self.transcribe_media(args.get("url_or_path", ""))
        elif name == "summarize_media":
            return self.summarize_media(args.get("url_or_path", ""))
        elif name == "audit_git_repositories":
            return self.audit_git_repositories(args.get("base_dir", "/media/darkseid/DATA/Repos"))
        elif name == "execute_sleep_routine":
            return self.execute_sleep_routine(shutdown_pc=args.get("shutdown_pc", False))
        elif name == "control_kasa_plug":
            return self.control_kasa_plug(args.get("device_name", "todos"), args.get("state", "off"))
        elif name == "control_keyboard_backlight":
            return self.control_keyboard_backlight(args.get("level", "off"))
        elif name == "get_gpu_status":
            return self.get_gpu_status()
        elif name == "get_system_status":
            return self.get_system_status()
        elif name == "send_email":
            return self.send_email(args.get("to_email", ""), args.get("subject", ""), args.get("body", ""))
        elif name == "send_desktop_notification":
            return self.send_desktop_notification(args.get("title", ""), args.get("message", ""))
        elif name == "create_whatsapp_link":
            return self.create_whatsapp_link(args.get("phone", ""), args.get("message", ""))
        elif name == "search_web":
            return self.search_web(args.get("query", ""))
        elif name == "run_shell_command":
            return self.run_shell_command(args.get("command", ""))
        else:
            return f"Función desconocida: {name}"
