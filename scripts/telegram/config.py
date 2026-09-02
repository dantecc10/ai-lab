"""
AI Lab — Telegram Bot Configuration Module
Carga y gestiona la configuración desde archivo INI o variables de entorno.
"""

import os
import configparser
from pathlib import Path
from dataclasses import dataclass, field

USER_CONF_PATH = Path.home() / ".config" / "ai-lab" / "telegram.conf"
REPO_CONF_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "telegram.conf"


@dataclass
class TelegramConfig:
    bot_token: str = ""
    allowed_users: set[int] = field(default_factory=set)
    strict_access: bool = True
    notify_admin_on_unauthorized: bool = True

    # AI settings
    llm_url: str = "http://127.0.0.1:9090/v1"
    model_name: str = "/home/darkseid/llama.cpp/ai-models/gemma-4-12b-it-Q4_K_M.gguf"
    fallback_llm_url: str = "http://127.0.0.1:9091/v1"
    fallback_model_name: str = "/home/darkseid/llama.cpp/ai-models/google_gemma-4-E4B-it-Q4_K_M.gguf"
    temperature: float = 0.7
    top_p: float = 0.95
    max_tokens: int = 4096
    system_prompt_file: str = "/home/darkseid/ai-lab/configs/system-prompt.txt"

    # Voice settings
    whisper_url: str = "http://127.0.0.1:9093/v1/audio/transcriptions"
    auto_voice_reply: bool = False
    piper_model: str = "/home/darkseid/ai-lab/scripts/voice/tts_models/es_MX-ald-medium.onnx"
    piper_config: str = "/home/darkseid/ai-lab/scripts/voice/tts_models/es_MX-ald-medium.onnx.json"

    # Vision settings
    enable_multimodal: bool = True
    media_dir: str = str(Path.home() / ".local" / "share" / "ai-lab" / "media")

    # Features
    enable_tools: bool = True
    enable_screenshot: bool = True
    max_history_turns: int = 40

    # Compaction settings
    context_window: int = 65536
    compaction_threshold: float = 0.80
    compaction_keep_recent_turns: int = 3
    enable_auto_compaction: bool = True

    def is_user_allowed(self, user_id: int) -> bool:
        """Verifica si un usuario de Telegram tiene permisos de acceso."""
        if not self.strict_access or not self.allowed_users:
            return True
        return user_id in self.allowed_users

    def get_admin_id(self) -> int | None:
        """Obtiene el ID del primer administrador configurado, si existe."""
        if self.allowed_users:
            return next(iter(self.allowed_users))
        return None

    def get_system_prompt(self) -> str:
        """Carga el system prompt desde el archivo configurado o retorna un fallback."""
        try:
            p = Path(self.system_prompt_file).expanduser().resolve()
            if p.exists():
                return p.read_text(encoding="utf-8").strip()
        except Exception:
            pass
        return (
            "Eres el Asistente AI personal de AI Lab. Hablas en español de México de manera concisa, "
            "útil y precisa. Tienes acceso al sistema local del usuario y puedes responder preguntas, "
            "analizar imágenes y procesar notas de voz."
        )


def get_config_path() -> Path:
    """Retorna la ruta al archivo de configuración activo."""
    if USER_CONF_PATH.exists():
        return USER_CONF_PATH
    if REPO_CONF_PATH.exists():
        return REPO_CONF_PATH
    # Si no existe ninguno, usar USER_CONF_PATH
    USER_CONF_PATH.parent.mkdir(parents=True, exist_ok=True)
    return USER_CONF_PATH


def load_config() -> TelegramConfig:
    """Lee y parsea la configuración del bot."""
    conf_path = get_config_path()
    cfg = TelegramConfig()

    parser = configparser.ConfigParser()
    if conf_path.exists():
        parser.read(conf_path, encoding="utf-8")

    # [telegram]
    cfg.bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", parser.get("telegram", "bot_token", fallback="")).strip()
    
    raw_users = os.environ.get("TELEGRAM_ALLOWED_USERS", parser.get("telegram", "allowed_users", fallback="")).strip()
    if raw_users:
        users = set()
        for u in raw_users.split(","):
            u_clean = u.strip()
            if u_clean.isdigit() or (u_clean.startswith("-") and u_clean[1:].isdigit()):
                users.add(int(u_clean))
        cfg.allowed_users = users

    cfg.strict_access = parser.getboolean("telegram", "strict_access", fallback=True)
    cfg.notify_admin_on_unauthorized = parser.getboolean("telegram", "notify_admin_on_unauthorized", fallback=True)

    # [ai]
    cfg.llm_url = os.environ.get("LLAMA_URL", parser.get("ai", "llm_url", fallback=cfg.llm_url)).strip()
    cfg.model_name = parser.get("ai", "model_name", fallback=cfg.model_name).strip()
    cfg.fallback_llm_url = parser.get("ai", "fallback_llm_url", fallback=cfg.fallback_llm_url).strip()
    cfg.fallback_model_name = parser.get("ai", "fallback_model_name", fallback=cfg.fallback_model_name).strip()
    cfg.temperature = parser.getfloat("ai", "temperature", fallback=cfg.temperature)
    cfg.top_p = parser.getfloat("ai", "top_p", fallback=cfg.top_p)
    cfg.max_tokens = parser.getint("ai", "max_tokens", fallback=cfg.max_tokens)
    cfg.system_prompt_file = parser.get("ai", "system_prompt_file", fallback=cfg.system_prompt_file).strip()

    # [voice]
    cfg.whisper_url = parser.get("voice", "whisper_url", fallback=cfg.whisper_url).strip()
    cfg.auto_voice_reply = parser.getboolean("voice", "auto_voice_reply", fallback=cfg.auto_voice_reply)
    cfg.piper_model = parser.get("voice", "piper_model", fallback=cfg.piper_model).strip()
    cfg.piper_config = parser.get("voice", "piper_config", fallback=cfg.piper_config).strip()

    # [vision]
    cfg.enable_multimodal = parser.getboolean("vision", "enable_multimodal", fallback=cfg.enable_multimodal)
    cfg.media_dir = parser.get("vision", "media_dir", fallback=cfg.media_dir).strip()

    # [features]
    cfg.enable_tools = parser.getboolean("features", "enable_tools", fallback=cfg.enable_tools)
    cfg.enable_screenshot = parser.getboolean("features", "enable_screenshot", fallback=cfg.enable_screenshot)
    cfg.max_history_turns = parser.getint("features", "max_history_turns", fallback=cfg.max_history_turns)
    cfg.context_window = parser.getint("features", "context_window", fallback=cfg.context_window)
    cfg.compaction_threshold = parser.getfloat("features", "compaction_threshold", fallback=cfg.compaction_threshold)
    cfg.compaction_keep_recent_turns = parser.getint("features", "compaction_keep_recent_turns", fallback=cfg.compaction_keep_recent_turns)
    cfg.enable_auto_compaction = parser.getboolean("features", "enable_auto_compaction", fallback=cfg.enable_auto_compaction)

    # Asegurar directorio de media
    Path(cfg.media_dir).mkdir(parents=True, exist_ok=True)

    return cfg


def save_token(token: str) -> None:
    """Guarda el token de Telegram en el archivo de configuración."""
    conf_path = get_config_path()
    parser = configparser.ConfigParser()
    if conf_path.exists():
        parser.read(conf_path, encoding="utf-8")
    
    if not parser.has_section("telegram"):
        parser.add_section("telegram")
    
    parser.set("telegram", "bot_token", token.strip())
    
    with open(conf_path, "w", encoding="utf-8") as f:
        parser.write(f)


def add_allowed_user(user_id: int) -> None:
    """Añade un ID de usuario a la lista blanca de telegram.conf."""
    conf_path = get_config_path()
    parser = configparser.ConfigParser()
    if conf_path.exists():
        parser.read(conf_path, encoding="utf-8")
    
    if not parser.has_section("telegram"):
        parser.add_section("telegram")
    
    raw_users = parser.get("telegram", "allowed_users", fallback="")
    users = [u.strip() for u in raw_users.split(",") if u.strip()]
    if str(user_id) not in users:
        users.append(str(user_id))
        parser.set("telegram", "allowed_users", ", ".join(users))
        with open(conf_path, "w", encoding="utf-8") as f:
            parser.write(f)
