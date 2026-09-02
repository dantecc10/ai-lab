"""
AI Lab — Telegram Bot Principal
Integra LLM local (Gemma 4 en llama.cpp), Whisper STT, Visión multimodal, Tools del sistema y Memoria.
"""

import os
import sys
import asyncio
import logging
import tempfile
from pathlib import Path
from typing import List

# Inyectar dependencias y ai-lab root
skills_venv = os.path.expanduser("~/scripting/gpu-tools/skills/.venv/lib/python3.12/site-packages")
if os.path.exists(skills_venv) and skills_venv not in sys.path:
    sys.path.insert(0, skills_venv)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from telegram import (
    Update,
    BotCommand,
    constants
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from telegram.error import TelegramError

from .config import load_config, TelegramConfig, add_allowed_user
from .memory import TelegramMemoryManager
from .tools_handler import ToolsHandler
from .llm_client import LLMClient
from .voice_handler import VoiceHandler
from .vision_handler import VisionHandler

# Logging
logging.basicConfig(
    format="%(asctime)s - [%(levelname)s] - %(name)s: %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("AILabTelegramBot")


class AILabTelegramBot:
    """Instancia principal del bot de Telegram para AI Lab."""

    def __init__(self):
        self.config: TelegramConfig = load_config()
        self.memory = TelegramMemoryManager(max_turns=self.config.max_history_turns)
        self.tools_handler = ToolsHandler()
        self.llm_client = LLMClient(self.config, self.tools_handler)
        self.voice_handler = VoiceHandler(whisper_url=self.config.whisper_url)
        self.vision_handler = VisionHandler(media_dir=self.config.media_dir)

    def _check_auth(self, update: Update) -> bool:
        """Comprueba si el usuario que envía el mensaje está autorizado."""
        user = update.effective_user
        if not user:
            return False
        return self.config.is_user_allowed(user.id)

    async def _handle_unauthorized(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Responde a usuarios no autorizados e informa al administrador."""
        user = update.effective_user
        if not user:
            return

        logger.warning(f"Acceso no autorizado intentado por: {user.full_name} (@{user.username}, ID: {user.id})")

        msg = (
            f"🔒 **Acceso No Autorizado**\n\n"
            f"Tu ID de Telegram es: `{user.id}`\n"
            f"Usuario: @{user.username or 'desconocido'}\n\n"
            f"Para habilitar tu acceso en el servidor AI Lab, añade tu ID en `telegram.conf` o ejecuta:\n"
            f"```bash\n~/ai-lab/scripts/telegram/telegram-ctl.sh allow-user {user.id}\n```"
        )
        await self._safe_reply(update, msg)

        # Notificar al administrador si está configurado
        admin_id = self.config.get_admin_id()
        if self.config.notify_admin_on_unauthorized and admin_id and admin_id != user.id:
            try:
                alert = (
                    f"⚠️ **Alerta de Seguridad — Intento de Acceso:**\n"
                    f"• Nombre: {user.full_name}\n"
                    f"• Usuario: @{user.username or 'N/A'}\n"
                    f"• ID: `{user.id}`\n"
                    f"Para autorizarlo, responde `/allow {user.id}`"
                )
                await context.bot.send_message(chat_id=admin_id, text=alert, parse_mode=constants.ParseMode.MARKDOWN)
            except Exception as e:
                logger.error(f"Error al notificar admin: {e}")

    async def _safe_reply(self, update: Update, text: str):
        """Envía un mensaje dividiéndolo si supera 4096 caracteres y con fallback a texto plano."""
        if not update.effective_message:
            return

        chunks = self._split_text(text, 4000)
        for chunk in chunks:
            try:
                await update.effective_message.reply_text(
                    chunk,
                    parse_mode=constants.ParseMode.MARKDOWN,
                    disable_web_page_preview=True
                )
            except TelegramError:
                # Fallback sin parse_mode si falla el formato markdown
                try:
                    await update.effective_message.reply_text(
                        chunk,
                        disable_web_page_preview=True
                    )
                except Exception as e:
                    logger.error(f"Error enviando mensaje: {e}")

    @staticmethod
    def _split_text(text: str, max_length: int = 4000) -> List[str]:
        """Divide textos largos respetando párrafos y saltos de línea."""
        if len(text) <= max_length:
            return [text]

        chunks = []
        current = ""
        for line in text.split("\n"):
            if len(current) + len(line) + 1 > max_length:
                if current:
                    chunks.append(current.strip())
                current = line + "\n"
            else:
                current += line + "\n"
        if current.strip():
            chunks.append(current.strip())
        return chunks

    # ── Handlers de Comandos ─────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /start: Bienvenida y estado inicial."""
        user = update.effective_user
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        welcome = (
            f"👋 ¡Hola, *{user.first_name}*!\n\n"
            f"🤖 Soy tu **Asistente de IA Local de AI Lab** ejecutándose en tu servidor local.\n\n"
            f"✨ **Capacidades:**\n"
            f"• 💬 *Chat & Razonamiento:* Gemma 4 12B en GPU con 65k contexto.\n"
            f"• 🎤 *Notas de Voz:* Transcripción con Whisper STT y respuestas de voz con Piper.\n"
            f"• 🖼️ *Visión & OCR:* Análisis multimodal de fotos, documentos y capturas.\n"
            f"• 🛠️ *Herramientas del Sistema:* Diagnóstico de GPU, comandos y estado.\n\n"
            f"📌 Tu ID de Telegram: `{user.id}`\n"
            f"Usa /help para explorar todos los comandos disponibles."
        )
        await self._safe_reply(update, welcome)

    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /help: Ayuda detallada."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        help_msg = (
            f"📖 *Comandos Disponibles en AI Lab Bot*\n\n"
            f"🔹 *Generales:*\n"
            f"• /start — Mensaje de bienvenida e ID\n"
            f"• /help — Muestra este menú de ayuda\n"
            f"• /myid — Muestra tu ID de usuario de Telegram\n"
            f"• /clear — Borra el historial y contexto de la conversación actual\n\n"
            f"🔹 *Diagnóstico & Sistema:*\n"
            f"• /status — Estado de los servicios de IA y recursos de hardware\n"
            f"• /gpu — Métricas de la GPU NVIDIA (VRAM, uso, temperatura, watts)\n"
            f"• /gitaudit — Audita los 130+ repositorios en `/media/darkseid/DATA/Repos`\n"
            f"• /screenshot — Captura la pantalla del escritorio y te envía la foto\n\n"
            f"🔹 *Control Nocturno & Dispositivos:*\n"
            f"• /sleep — Rutina de dormir (Lux OFF, ElektroDante ON, Luz Teclado OFF)\n"
            f"• /goodnight — Rutina de dormir + Apagado de computadora\n"
            f"• /kbd `<off/low/med/high>` — Ajusta el brillo del teclado de la PC\n"
            f"• /kasa `<lux/elektrodante/todos>` `<on/off>` — Control directo de enchufes\n\n"
            f"🔹 *Configuración & Modos:*\n"
            f"• /model — Muestra el modelo activo o alterna entre 12B (GPU) y E4B (CPU)\n"
            f"• /voice — Activa o desactiva las respuestas automáticas en nota de voz\n"
            f"• /cmd `<comando>` — Ejecuta un comando en la terminal (solo admins)\n"
            f"• /allow `<id>` — Autoriza a un nuevo usuario de Telegram\n\n"
            f"💡 *Consejo:* Puedes enviarme notas de voz 🎙️ o imágenes 📸 directamente y las procesaré de forma automática."
        )
        await self._safe_reply(update, help_msg)

    async def cmd_myid(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /myid: Devuelve el ID de Telegram."""
        user = update.effective_user
        if not user:
            return
        await self._safe_reply(
            update,
            f"👤 **Tu Información:**\n• **Nombre:** {user.full_name}\n• **Usuario:** @{user.username or 'N/A'}\n• **ID Telegram:** `{user.id}`"
        )

    async def cmd_clear(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /clear: Borra el contexto del chat."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        chat_id = update.effective_chat.id
        self.memory.clear_history(chat_id)
        await self._safe_reply(update, "🧹 *Memoria y contexto de conversación reiniciados.* Empecemos de nuevo.")

    async def cmd_compact(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /compact: Fuerza la compactación del contexto de la conversación actual."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        chat_id = update.effective_chat.id
        raw_history = self.memory.get_raw_cache(chat_id)
        keep_count = self.config.compaction_keep_recent_turns * 2

        if len(raw_history) <= keep_count:
            await self._safe_reply(update, "ℹ️ El historial actual es muy corto para requerir compactación.")
            return

        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        to_summarize = raw_history[:-keep_count]
        formatted = [{"role": m.role, "content": m.content} for m in to_summarize]

        summary = await self.llm_client.summarize_for_compaction(formatted)
        self.memory.compact_history(chat_id, summary, keep_recent_turns=self.config.compaction_keep_recent_turns)

        await self._safe_reply(
            update,
            f"🗜️ **Conversación compactada con éxito:**\n"
            f"• Se sintetizaron `{len(to_summarize)}` mensajes previos.\n"
            f"• Se conservan los últimos `{self.config.compaction_keep_recent_turns}` turnos intactos.\n"
            f"• El contexto se ha liberado para continuar la conversación indefinidamente."
        )

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /status: Estado de servicios y recursos."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        status_info = self.tools_handler.get_system_status()
        await self._safe_reply(update, status_info)

    async def cmd_gpu(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /gpu: Métricas de GPU NVIDIA."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        gpu_info = self.tools_handler.get_gpu_status()
        await self._safe_reply(update, gpu_info)

    async def cmd_screenshot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /screenshot: Captura de pantalla enviada por Telegram."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        await update.effective_chat.send_action(constants.ChatAction.UPLOAD_PHOTO)
        try:
            shot_path = self.vision_handler.capture_desktop_screenshot()
            with open(shot_path, "rb") as photo_file:
                await update.effective_message.reply_photo(
                    photo=photo_file,
                    caption=f"📸 *Captura de Pantalla del Escritorio*\n`{shot_path.name}`",
                    parse_mode=constants.ParseMode.MARKDOWN
                )
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error al capturar pantalla: {e}")

    async def cmd_model(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /model: Ver o cambiar modelo activo."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        args = context.args
        if args and args[0].lower() in ["e4b", "cpu", "subagent", "9091"]:
            self.llm_client.switch_model(use_fallback=True)
            await self._safe_reply(update, f"🔄 Modelo cambiado a **Gemma 4 E4B (CPU :9091)**")
        elif args and args[0].lower() in ["12b", "gpu", "main", "9090"]:
            self.llm_client.switch_model(use_fallback=False)
            await self._safe_reply(update, f"🔄 Modelo cambiado a **Gemma 4 12B (GPU :9090)**")
        else:
            current = self.llm_client.active_endpoint
            model = self.llm_client.active_model.split("/")[-1]
            await self._safe_reply(
                update,
                f"🧠 *Modelo LLM Activo:*\n• **Endpoint:** `{current}`\n• **Modelo:** `{model}`\n\n"
                f"Para cambiar, usa:\n• `/model 12b` (GPU principal)\n• `/model e4b` (CPU sub-agente)"
            )

    async def cmd_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /voice: Alterna respuestas de voz."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        user_id = update.effective_user.id
        current = self.memory.get_user_preference(user_id, "voice_reply_enabled", default=self.config.auto_voice_reply)
        new_val = not current
        self.memory.set_user_preference(user_id, "voice_reply_enabled", new_val)

        state = "activadas 🔊" if new_val else "desactivadas 🔇"
        await self._safe_reply(update, f"🎙️ Respuestas en nota de voz **{state}** para este chat.")

    async def cmd_allow(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /allow <id>: Añade un usuario a la whitelist."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        args = context.args
        if not args or not (args[0].isdigit() or (args[0].startswith("-") and args[0][1:].isdigit())):
            await self._safe_reply(update, "Uso: `/allow <telegram_user_id>`")
            return

        new_id = int(args[0])
        add_allowed_user(new_id)
        self.config.allowed_users.add(new_id)
        await self._safe_reply(update, f"✅ Usuario `{new_id}` añadido exitosamente a la lista blanca.")

    async def cmd_exec(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /cmd <comando>: Ejecución directa en terminal."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        if not context.args:
            await self._safe_reply(update, "Uso: `/cmd <comando bash>`\nEjemplo: `/cmd uptime`")
            return

        cmd_str = " ".join(context.args)
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        result = self.tools_handler.run_safe_command(cmd_str)
        await self._safe_reply(update, result)

    async def cmd_sleep(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /sleep: Rutina nocturna (Lux OFF, ElektroDante ON, Luz Teclado OFF, PC encendida)."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        res = self.tools_handler.execute_sleep_routine(shutdown_pc=False)
        await self._safe_reply(update, res)

    async def cmd_goodnight(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /goodnight: Rutina nocturna + Apagado de computadora."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        res = self.tools_handler.execute_sleep_routine(shutdown_pc=True)
        await self._safe_reply(update, res)

    async def cmd_kbd(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /kbd <off|low|med|high>: Controla la luz del teclado ASUS."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        level = context.args[0].lower() if context.args else "off"
        res = self.tools_handler.control_keyboard_backlight(level)
        await self._safe_reply(update, res)

    async def cmd_kasa(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /kasa <lux|elektrodante|todos> <on|off>: Control directo de enchufes."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if len(context.args) < 2:
            await self._safe_reply(update, "Uso: `/kasa <dispositivo> <on|off>`\nEjemplo: `/kasa lux off` o `/kasa todos on`")
            return
        dev, state = context.args[0], context.args[1]
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        res = self.tools_handler.control_kasa_plug(dev, state)
        await self._safe_reply(update, res)

    async def cmd_gitaudit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /gitaudit: Audita todos los repositorios en /media/darkseid/DATA/Repos."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        res = self.tools_handler.audit_git_repositories()
        await self._safe_reply(update, res)

    # ── Recordatorios y Temporizadores ───────────────────────────

    async def cmd_reminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /reminder <tiempo> <mensaje> o /timer <minutos> [mensaje]."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "⏰ **Uso:** `/reminder <tiempo> <mensaje>`\nEjemplos:\n• `/reminder 15m Sacar la pizza del horno`\n• `/reminder 2h Revisar entrenamiento`\n• `/reminder 18:30 Junta con el equipo`")
            return

        time_arg = context.args[0]
        text_arg = " ".join(context.args[1:]) if len(context.args) > 1 else "Temporizador finalizado"
        user_id = update.effective_user.id

        from scripts.tools.reminder_engine import reminder_engine
        try:
            res = reminder_engine.add_reminder(title=text_arg, due=time_arg, priority="important", user_id=user_id)
            await self._safe_reply(
                update,
                f"⏰ **Recordatorio programado:**\n• **ID:** `#{res['id']}`\n• **Tarea:** *{res['title']}*\n• **Vence en:** `{res['time_left']}` ({res['due_at']})"
            )
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error: {e}")

    async def cmd_reminders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /reminders: Lista recordatorios pendientes."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        from scripts.tools.reminder_engine import reminder_engine
        items = reminder_engine.list_pending_reminders(user_id=update.effective_user.id)
        if not items:
            await self._safe_reply(update, "ℹ️ No tienes recordatorios ni temporizadores pendientes.")
            return
        lines = [f"📋 **Recordatorios Pendientes ({len(items)}):**\n"]
        for i in items:
            lines.append(f"• `[#{i['id']}]` *{i['title']}* ➔ Vence en `{i['time_left']}` ({i['due_at']})")
        lines.append("\n_Para cancelar uno, usa /cancel `<id>`_")
        await self._safe_reply(update, "\n".join(lines))

    async def cmd_cancelreminder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /cancel <id>: Cancela un recordatorio."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args or not context.args[0].isdigit():
            await self._safe_reply(update, "Uso: `/cancel <ID>` (Ej: `/cancel 1`)")
            return
        r_id = int(context.args[0])
        from scripts.tools.reminder_engine import reminder_engine
        ok = reminder_engine.cancel_reminder(r_id)
        if ok:
            await self._safe_reply(update, f"✅ Recordatorio `#{r_id}` cancelado exitosamente.")
        else:
            await self._safe_reply(update, f"ℹ️ No se encontró el recordatorio `#{r_id}`.")

    # ── Dev Ops & Telemetría ─────────────────────────────────────

    async def cmd_dev(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /dev o /sys: Telemetría de hardware, GPU, RAM, disco y servicios."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        from scripts.tools.dev_controller import dev_controller
        res = dev_controller.get_system_telemetry()
        await self._safe_reply(update, res)

    async def cmd_top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /top: Muestra los procesos principales en CPU y RAM."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        from scripts.tools.dev_controller import dev_controller
        res = dev_controller.get_top_processes(count=5)
        await self._safe_reply(update, res)

    async def cmd_service(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /service <nombre> <action>: Control de servicios systemd."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "Uso: `/service <gemma4|e4b|whisper|telegram|git-sentinel> <status|restart|logs|stop|start>`")
            return
        svc = context.args[0]
        act = context.args[1] if len(context.args) > 1 else "status"
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        from scripts.tools.dev_controller import dev_controller
        res = dev_controller.manage_service(svc, act)
        await self._safe_reply(update, res)

    async def cmd_sh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /sh <comando>: Ejecución remota de consola."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "Uso: `/sh <comando_bash>`")
            return
        cmd_str = " ".join(context.args)
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        from scripts.tools.dev_controller import dev_controller
        res = dev_controller.execute_shell_command(cmd_str)
        await self._safe_reply(update, res)

    # ── Multimedia & YouTube (Whisper + yt-dlp) ──────────────────

    async def cmd_yt(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /yt <url> [audio/video]: Descarga multimedia con yt-dlp."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "Uso: `/yt <URL_YOUTUBE> [audio|video]`")
            return
        url = context.args[0]
        mtype = context.args[1].lower() if len(context.args) > 1 and context.args[1].lower() in ["audio", "video"] else "audio"
        await update.effective_chat.send_action(constants.ChatAction.RECORD_VOICE if mtype == "audio" else constants.ChatAction.UPLOAD_DOCUMENT)
        await self._safe_reply(update, f"⏳ Descargando `{mtype}` con yt-dlp... Espera un momento.")
        from scripts.tools.media_processor import media_processor
        try:
            res = media_processor.download_media(url, media_type=mtype)
            await self._safe_reply(
                update,
                f"✅ **Descarga lista:**\n• **Título:** *{res['title']}*\n• **Canal:** `{res['uploader']}`\n• **Tamaño:** `{res['file_size_mb']} MB`\n• **Guardado en:** `{res['file_path']}`"
            )
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error en descarga: {e}")

    async def cmd_ytranscribe(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /ytranscribe <url>: Transcribe un video con Whisper STT."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "Uso: `/ytranscribe <URL_YOUTUBE>`")
            return
        url = context.args[0]
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        await self._safe_reply(update, "🎙️ Extrayendo audio y transcribiendo con Whisper STT local (:9093)...")
        from scripts.tools.media_processor import media_processor
        try:
            res = media_processor.process_and_transcribe(url)
            text_preview = res["text"][:3000]
            await self._safe_reply(
                update,
                f"📝 **Transcripción de:** *{res['title']}*\n• **Palabras:** `{res['word_count']}`\n\n{text_preview}"
            )
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error transcribiendo: {e}")

    async def cmd_ysummarize(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /ysummarize <url>: Transcribe y genera resumen inteligente con Gemma 4."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "Uso: `/ysummarize <URL_YOUTUBE>`")
            return
        url = context.args[0]
        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        await self._safe_reply(update, "🧠 Descargando audio, transcribiendo con Whisper y generando resumen inteligente con Gemma 4...")
        from scripts.tools.media_processor import media_processor
        try:
            res = media_processor.summarize_video_or_audio(url)
            await self._safe_reply(update, res.get("summary", "Sin resumen."))
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error resumiendo contenido: {e}")

    # ── Generación de Imagen & Voz Creativa ──────────────────────

    async def cmd_imagine(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /imagine <prompt>: Genera una imagen por difusión local."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "🎨 **Uso:** `/imagine <descripción de la imagen>`\nEjemplo: `/imagine un robot cyberpunk en un laboratorio con luces de neón cian, 8k fotorrealista`")
            return

        prompt_str = " ".join(context.args)
        await update.effective_chat.send_action(constants.ChatAction.UPLOAD_PHOTO)
        await self._safe_reply(update, f"🎨 Generando imagen para: *\"{prompt_str}\"*... Espera unos segundos.")

        from scripts.tools.image_generator import image_generator
        try:
            res = image_generator.generate_image(prompt=prompt_str, aspect_ratio="1:1")
            img_path = res.get("file_path")
            if img_path and os.path.exists(img_path):
                with open(img_path, "rb") as photo_file:
                    caption = f"🎨 *{res['prompt']}*\n⏱️ Renderizado en `{res['gen_time_sec']}s` ({res['width']}x{res['height']})"
                    await update.effective_message.reply_photo(photo=photo_file, caption=caption, parse_mode=constants.ParseMode.MARKDOWN)
            else:
                await self._safe_reply(update, "⚠️ No se pudo obtener el archivo de imagen generado.")
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error generando imagen: {e}")

    async def cmd_voicegen(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /voicegen [voz] <texto>: Genera audio de alta fidelidad con Kokoro-82M."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "🎙️ **Uso:** `/voicegen [voz] <texto>`\nEjemplos:\n• `/voicegen Hola Dante, este es el nuevo audio de estudio.`\n• `/voicegen em_alex Buenos días a todos.`\n\nUsa `/voices` para ver el catálogo de voces.")
            return

        first_arg = context.args[0].lower()
        from scripts.voice.creative_voice_engine import creative_voice_engine
        if first_arg in creative_voice_engine.VOICE_CATALOG:
            voice_id = first_arg
            text_str = " ".join(context.args[1:])
        else:
            voice_id = "ef_dora"
            text_str = " ".join(context.args)

        if not text_str.strip():
            await self._safe_reply(update, "⚠️ Debes ingresar el texto que deseas sintetizar.")
            return

        await update.effective_chat.send_action(constants.ChatAction.RECORD_VOICE)
        try:
            res = creative_voice_engine.synthesize(text=text_str, voice=voice_id, output_format="ogg")
            audio_path = res.get("file_path")
            if audio_path and os.path.exists(audio_path):
                with open(audio_path, "rb") as vf:
                    caption = f"🎙️ Voz: *{res['voice_name']}* ({res['style']}) • `{res['duration_sec']}s`"
                    await update.effective_message.reply_voice(voice=vf, caption=caption, parse_mode=constants.ParseMode.MARKDOWN)
            else:
                await self._safe_reply(update, "⚠️ No se pudo generar el archivo de voz.")
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error generando voz de alta fidelidad: {e}")

    async def cmd_voices(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /voices: Muestra el catálogo de voces de alta fidelidad disponibles."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        from scripts.voice.creative_voice_engine import creative_voice_engine
        msg_lines = ["🎙️ **Catálogo de Voces de Estudio (Kokoro-82M):**\n"]
        msg_lines.append("🇪🇸 **Español:**")
        for vid, v in creative_voice_engine.VOICE_CATALOG.items():
            if v["lang"] == "e":
                msg_lines.append(f"• `{vid}`: **{v['name']}** ({v['gender']}) — _{v['style']}_")

        msg_lines.append("\n🇺🇸 **Inglés Americano:**")
        for vid, v in creative_voice_engine.VOICE_CATALOG.items():
            if v["lang"] == "a":
                msg_lines.append(f"• `{vid}`: **{v['name']}** ({v['gender']}) — _{v['style']}_")

        msg_lines.append("\n🇬🇧 **Inglés Británico:**")
        for vid, v in creative_voice_engine.VOICE_CATALOG.items():
            if v["lang"] == "b":
                msg_lines.append(f"• `{vid}`: **{v['name']}** ({v['gender']}) — _{v['style']}_")

        msg_lines.append("\n💡 **Uso:** `/voicegen <voz> <texto>` o `/speak <voz> <mensaje>`")
        await self._safe_reply(update, "\n".join(msg_lines))

    async def cmd_speak(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Comando /speak [voz] <texto>: Emite un anuncio por los altavoces de la PC con aviso visual."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return
        if not context.args:
            await self._safe_reply(update, "🔊 **Uso:** `/speak [voz] <mensaje>`\nEjemplos:\n• `/speak bm_george System alert, build finished.`\n• `/speak em_santa Atención Dante, proceso completado.`")
            return

        from scripts.voice.creative_voice_engine import creative_voice_engine
        first_arg = context.args[0].lower()
        if first_arg in creative_voice_engine.VOICE_CATALOG:
            voice_id = first_arg
            msg_str = " ".join(context.args[1:])
        else:
            # Si el texto parece inglés, usar bm_george; si no, em_santa
            text_preview = " ".join(context.args)
            voice_id = "bm_george" if any(w in text_preview.lower().split() for w in ["system", "alert", "hello", "warning", "ready", "complete", "finished", "the", "is", "test"]) else "em_santa"
            msg_str = text_preview

        if not msg_str.strip():
            await self._safe_reply(update, "⚠️ Debes ingresar el mensaje a pronunciar.")
            return

        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        try:
            res = self.tools_handler.speak_notification(message=msg_str, voice=voice_id, visual_style="synthwave")
            await self._safe_reply(update, res)
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error emitiendo anuncio por altavoces: {e}")

    # ── Handlers de Mensajes ─────────────────────────────────────

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Procesa mensajes de texto del usuario."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        user_text = update.effective_message.text
        if not user_text:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        await update.effective_chat.send_action(constants.ChatAction.TYPING)

        # 1. Guardar mensaje de usuario en memoria
        self.memory.add_message(chat_id, user_id, "user", user_text)

        # 2. Obtener historial contextual con prompt del sistema
        system_prompt = self.config.get_system_prompt()
        messages = self.memory.get_context_messages(chat_id, system_prompt)

        # 3. Generar respuesta con el LLM
        reply_text = await self.llm_client.generate_response(messages)

        # 4. Guardar respuesta del asistente en memoria
        self.memory.add_message(chat_id, user_id, "assistant", reply_text)

        # 5. Enviar respuesta por Telegram
        await self._safe_reply(update, reply_text)

        # 6. Si el modo de voz está activo, sintetizar y enviar nota de voz
        voice_enabled = self.memory.get_user_preference(user_id, "voice_reply_enabled", default=self.config.auto_voice_reply)
        if voice_enabled:
            await self._send_voice_reply(update, reply_text)

        # 7. Auto-compaction si el contexto supera el 80%
        await self._check_and_auto_compact(update, chat_id)

    async def handle_voice(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Procesa notas de voz entrantes (Speech-to-Text) y responde."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        voice = update.effective_message.voice or update.effective_message.audio
        if not voice:
            return

        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        await update.effective_chat.send_action(constants.ChatAction.RECORD_VOICE)

        # 1. Descargar archivo de audio de Telegram
        file = await context.bot.get_file(voice.file_id)
        temp_dir = Path(tempfile.gettempdir()) / "ai_lab_telegram_in"
        temp_dir.mkdir(parents=True, exist_ok=True)
        local_audio_path = temp_dir / f"voice_{voice.file_unique_id}.oga"
        await file.download_to_drive(custom_path=local_audio_path)

        # 2. Transcribir con Whisper
        try:
            transcription = self.voice_handler.transcribe(local_audio_path)
        except Exception as e:
            await self._safe_reply(update, f"⚠️ Error al transcribir el audio: {e}")
            return

        # Mostrar transcripción reconocida
        await self._safe_reply(update, f"🎤 *Transcripción:* \"_{transcription}_\"")

        # 3. Enviar a la IA
        self.memory.add_message(chat_id, user_id, "user", f"[Nota de voz transcrita]: {transcription}")
        system_prompt = self.config.get_system_prompt()
        messages = self.memory.get_context_messages(chat_id, system_prompt)

        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        reply_text = await self.llm_client.generate_response(messages)
        self.memory.add_message(chat_id, user_id, "assistant", reply_text)

        # 4. Responder con texto
        await self._safe_reply(update, reply_text)

        # 5. Siempre intentar responder con audio si el usuario mandó audio
        await self._send_voice_reply(update, reply_text)

        # 6. Auto-compaction si el contexto supera el 80%
        await self._check_and_auto_compact(update, chat_id)

    async def handle_photo(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Procesa imágenes y fotos con Visión Multimodal y OCR."""
        if not self._check_auth(update):
            await self._handle_unauthorized(update, context)
            return

        photos = update.effective_message.photo
        if not photos:
            return

        # Tomar la imagen de mayor resolución
        photo = photos[-1]
        caption = update.effective_message.caption or ""
        chat_id = update.effective_chat.id
        user_id = update.effective_user.id

        await update.effective_chat.send_action(constants.ChatAction.UPLOAD_PHOTO)

        # 1. Descargar foto
        file = await context.bot.get_file(photo.file_id)
        temp_dir = Path(tempfile.gettempdir()) / "ai_lab_telegram_photos"
        temp_dir.mkdir(parents=True, exist_ok=True)
        photo_path = temp_dir / f"photo_{photo.file_unique_id}.jpg"
        await file.download_to_drive(custom_path=photo_path)

        # 2. Procesar con Visión y OCR
        vision_data = self.vision_handler.process_image(photo_path, user_prompt=caption)

        # 3. Preparar prompt enriquecido para el LLM
        prompt_with_image = f"[El usuario envió una imagen: {vision_data['filename']}]\n\n"
        if vision_data.get("analysis"):
            prompt_with_image += f"Análisis Visual:\n{vision_data['analysis']}\n\n"
        if vision_data.get("ocr"):
            prompt_with_image += f"Texto Detectado en la Imagen (OCR):\n{vision_data['ocr']}\n\n"
        if caption:
            prompt_with_image += f"Pregunta/Instrucción del usuario:\n{caption}"

        self.memory.add_message(chat_id, user_id, "user", prompt_with_image)
        system_prompt = self.config.get_system_prompt()
        messages = self.memory.get_context_messages(chat_id, system_prompt)

        await update.effective_chat.send_action(constants.ChatAction.TYPING)
        reply_text = await self.llm_client.generate_response(messages)
        self.memory.add_message(chat_id, user_id, "assistant", reply_text)

        await self._safe_reply(update, reply_text)

        # 4. Auto-compaction si el contexto supera el 80%
        await self._check_and_auto_compact(update, chat_id)

    async def _check_and_auto_compact(self, update: Update, chat_id: int):
        """Verifica si el uso de tokens alcanzó el umbral (80%) y ejecuta auto-compaction."""
        if not getattr(self.config, "enable_auto_compaction", True):
            return

        usage = getattr(self.llm_client, "last_usage", None)
        if not usage:
            return

        total_tokens = getattr(usage, "total_tokens", 0) or (getattr(usage, "prompt_tokens", 0) + getattr(usage, "completion_tokens", 0))
        limit = getattr(self.config, "context_window", 65536)
        if total_tokens <= 0 or limit <= 0:
            return

        threshold = getattr(self.config, "compaction_threshold", 0.80)
        ratio = total_tokens / limit
        if ratio >= threshold:
            raw_history = self.memory.get_raw_cache(chat_id)
            keep_count = getattr(self.config, "compaction_keep_recent_turns", 3) * 2
            if len(raw_history) <= keep_count:
                return

            to_summarize = raw_history[:-keep_count]
            formatted = [{"role": m.role, "content": m.content} for m in to_summarize]
            pct = int(ratio * 100)

            summary = await self.llm_client.summarize_for_compaction(formatted)
            self.memory.compact_history(chat_id, summary, keep_recent_turns=self.config.compaction_keep_recent_turns)

            await self._safe_reply(
                update,
                f"🗜️ **Auto-Compaction Activado ({pct}% de {limit} tokens usado):**\n"
                f"Se han sintetizado `{len(to_summarize)}` mensajes previos en memoria para prolongar la conversación indefinidamente."
            )

    async def _send_voice_reply(self, update: Update, text: str):
        """Genera y envía una nota de voz como respuesta."""
        try:
            await update.effective_chat.send_action(constants.ChatAction.RECORD_VOICE)
            voice_file = self.voice_handler.synthesize(text)
            if voice_file and voice_file.exists():
                with open(voice_file, "rb") as vf:
                    await update.effective_message.reply_voice(voice=vf)
        except Exception as e:
            logger.warning(f"No se pudo enviar nota de voz de respuesta: {e}")

    async def post_init(self, application):
        """Configura el menú de comandos en la UI de Telegram al iniciar y arranca el despachador de recordatorios."""
        commands = [
            BotCommand("start", "Iniciar bot y ver ID"),
            BotCommand("help", "Guía completa de comandos"),
            BotCommand("reminder", "Temporizador/recordatorio: /reminder 15m pizza"),
            BotCommand("reminders", "Ver recordatorios pendientes"),
            BotCommand("cancel", "Cancelar recordatorio: /cancel <id>"),
            BotCommand("dev", "Dashboard de telemetría de hardware y servicios"),
            BotCommand("service", "Gestión de servicios: /service <svc> <action>"),
            BotCommand("top", "Top procesos en CPU y RAM"),
            BotCommand("imagine", "Generar imagen con IA: /imagine <prompt>"),
            BotCommand("voicegen", "Generar voz de estudio: /voicegen <texto>"),
            BotCommand("voices", "Ver catálogo de voces de alta fidelidad"),
            BotCommand("speak", "Notificación hablada en PC: /speak [voz] <msg>"),
            BotCommand("yt", "Descarga YouTube: /yt <url> [audio/video]"),
            BotCommand("ytranscribe", "Transcribir video con Whisper STT"),
            BotCommand("ysummarize", "Resumir video inteligente con Gemma 4"),
            BotCommand("sleep", "Rutina de dormir (Luz OFF, Teclado OFF)"),
            BotCommand("goodnight", "Rutina de dormir + Apagar PC"),
            BotCommand("gitaudit", "Auditar repositorios Git en DATA/Repos"),
            BotCommand("kbd", "Brillo teclado: /kbd off|low|high"),
            BotCommand("kasa", "Control enchufes: /kasa <dev> <on|off>"),
            BotCommand("status", "Estado de servicios y hardware"),
            BotCommand("gpu", "Métricas de GPU NVIDIA"),
            BotCommand("screenshot", "Captura de pantalla remota"),
            BotCommand("model", "Ver o cambiar modelo LLM"),
            BotCommand("voice", "Alternar respuestas en nota de voz"),
            BotCommand("compact", "Compactar historial y prolongar contexto"),
            BotCommand("clear", "Reiniciar conversación"),
            BotCommand("myid", "Ver tu ID de Telegram"),
        ]
        try:
            await application.bot.set_my_commands(commands)
            logger.info("Comandos de Telegram configurados correctamente en la interfaz.")
        except Exception as e:
            logger.warning(f"No se pudieron configurar los comandos en Telegram: {e}")

        # Iniciar despachador de recordatorios omnicanal hacia Telegram
        import asyncio
        main_loop = asyncio.get_running_loop()

        def _telegram_reminder_alert(reminder):
            u_id = reminder.get("user_id") or (list(self.config.allowed_users)[0] if self.config.allowed_users else None)
            if u_id:
                msg = f"⏰ **¡RECORDATORIO / TEMPORIZADOR!**\n\n📌 **Tarea:** *{reminder['title']}*\n⏱️ **Programado para:** `{reminder['due_at']}`"
                asyncio.run_coroutine_threadsafe(
                    application.bot.send_message(chat_id=u_id, text=msg, parse_mode=constants.ParseMode.MARKDOWN),
                    main_loop
                )

        from scripts.tools.reminder_engine import reminder_engine
        reminder_engine.start_background_watcher(interval_sec=3.0, telegram_callback=_telegram_reminder_alert)
        logger.info("Vigilante de recordatorios omnicanal iniciado en segundo plano.")

    def run(self):
        """Inicia el bot de Telegram con polling asíncrono."""
        token = self.config.bot_token
        if not token:
            print("\n❌ Error: No se ha configurado el token de Telegram (bot_token).")
            print("Configúralo editando `ai-lab/configs/telegram.conf` o ejecutando:")
            print("  ~/ai-lab/scripts/telegram/telegram-ctl.sh set-token <TU_BOT_TOKEN>\n")
            sys.exit(1)

        print("🚀 Iniciando AI Lab Telegram Bot...")
        print(f"• LLM Endpoint: {self.config.llm_url}")
        print(f"• Whisper STT: {self.config.whisper_url}")
        print(f"• Usuarios Permitidos: {list(self.config.allowed_users) or 'Todos (Acceso abierto)'}")

        app = ApplicationBuilder().token(token).post_init(self.post_init).build()

        # Comandos generales
        app.add_handler(CommandHandler("start", self.cmd_start))
        app.add_handler(CommandHandler("help", self.cmd_help))
        app.add_handler(CommandHandler("myid", self.cmd_myid))
        app.add_handler(CommandHandler("clear", self.cmd_clear))
        app.add_handler(CommandHandler("reset", self.cmd_clear))
        app.add_handler(CommandHandler("compact", self.cmd_compact))
        app.add_handler(CommandHandler("compaction", self.cmd_compact))
        app.add_handler(CommandHandler("model", self.cmd_model))
        app.add_handler(CommandHandler("voice", self.cmd_voice))
        app.add_handler(CommandHandler("allow", self.cmd_allow))

        # Recordatorios y Temporizadores
        app.add_handler(CommandHandler("reminder", self.cmd_reminder))
        app.add_handler(CommandHandler("timer", self.cmd_reminder))
        app.add_handler(CommandHandler("reminders", self.cmd_reminders))
        app.add_handler(CommandHandler("cancel", self.cmd_cancelreminder))
        app.add_handler(CommandHandler("cancelreminder", self.cmd_cancelreminder))

        # Dev Ops & Telemetría
        app.add_handler(CommandHandler("dev", self.cmd_dev))
        app.add_handler(CommandHandler("sys", self.cmd_dev))
        app.add_handler(CommandHandler("status", self.cmd_status))
        app.add_handler(CommandHandler("gpu", self.cmd_gpu))
        app.add_handler(CommandHandler("top", self.cmd_top))
        app.add_handler(CommandHandler("service", self.cmd_service))
        app.add_handler(CommandHandler("svc", self.cmd_service))
        app.add_handler(CommandHandler("sh", self.cmd_sh))
        app.add_handler(CommandHandler("cmd", self.cmd_sh))
        app.add_handler(CommandHandler("screenshot", self.cmd_screenshot))
        app.add_handler(CommandHandler("gitaudit", self.cmd_gitaudit))

        # Multimedia & YouTube
        app.add_handler(CommandHandler("yt", self.cmd_yt))
        app.add_handler(CommandHandler("ytranscribe", self.cmd_ytranscribe))
        app.add_handler(CommandHandler("ysummarize", self.cmd_ysummarize))

        # Generación de Imagen & Voz Creativa
        app.add_handler(CommandHandler("imagine", self.cmd_imagine))
        app.add_handler(CommandHandler("image", self.cmd_imagine))
        app.add_handler(CommandHandler("voicegen", self.cmd_voicegen))
        app.add_handler(CommandHandler("voices", self.cmd_voices))
        app.add_handler(CommandHandler("speak", self.cmd_speak))

        # Smart Home & Sleep
        app.add_handler(CommandHandler("sleep", self.cmd_sleep))
        app.add_handler(CommandHandler("goodnight", self.cmd_goodnight))
        app.add_handler(CommandHandler("kbd", self.cmd_kbd))
        app.add_handler(CommandHandler("kasa", self.cmd_kasa))

        # Mensajes
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_text))
        app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, self.handle_voice))
        app.add_handler(MessageHandler(filters.PHOTO, self.handle_photo))

        app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    bot = AILabTelegramBot()
    bot.run()
