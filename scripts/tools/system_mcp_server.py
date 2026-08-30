#!/usr/bin/env python3
"""
MCP Server para sistema — Stdio transport para llama.cpp
Lee JSON-RPC de stdin, escribe respuestas a stdout.
Tools: filesystem navigation, file operations, command execution, system/gpu info.
"""

import sys
import json
import os
import subprocess
import shutil
import glob
import time
import base64
import hashlib
from datetime import datetime
from urllib.parse import quote

# Add venv site-packages for duckduckgo-search
venv_site = "/tmp/search-env/lib/python3.12/site-packages"
if os.path.exists(venv_site) and venv_site not in sys.path:
    sys.path.insert(0, venv_site)

# ── Configuración ─────────────────────────────────────────
HOME = os.path.expanduser("~")
BASE_DIR = HOME
MAX_OUTPUT_LINES = 500
MAX_FILE_SIZE = 1024 * 1024  # 1MB max read
COMMAND_TIMEOUT = 30

# ── Fernet Encryption ─────────────────────────────────────
FERNET_KEY_PATH = os.path.join(HOME, ".local/share/chatmanager/secret_key")

def _get_fernet():
    """Get or create Fernet instance for encryption."""
    try:
        from cryptography.fernet import Fernet
        os.makedirs(os.path.dirname(FERNET_KEY_PATH), exist_ok=True)
        
        if os.path.exists(FERNET_KEY_PATH):
            with open(FERNET_KEY_PATH, "rb") as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(FERNET_KEY_PATH, "wb") as f:
                f.write(key)
            os.chmod(FERNET_KEY_PATH, 0o600)
        
        return Fernet(key)
    except ImportError:
        return None

def encrypt_value(value: str) -> str:
    """Encrypt a string value."""
    fernet = _get_fernet()
    if fernet:
        return fernet.encrypt(value.encode()).decode()
    return base64.b64encode(value.encode()).decode()

def decrypt_value(encrypted: str) -> str:
    """Decrypt a string value."""
    fernet = _get_fernet()
    if fernet:
        try:
            return fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            pass
    try:
        return base64.b64decode(encrypted.encode()).decode()
    except Exception:
        return encrypted

BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "dd if=", "mkfs", "chmod 777",
    "> /dev/sd", ":(){ :|:& };:", "mv / ", "rm -r /home",
    "rm -rf ~", "rm -rf /root"
]

DESTRUCTIVE_PATTERNS = ["rm ", "mv ", "chmod ", "chown ", "kill ", "pkill ", "> ", ">> "]

LOG_FILE = os.path.join(HOME, ".config/system-tools.log")


# ── Auto-Notification System ───────────────────────────────
NOTIFY_CONFIG_PATH = os.path.join(HOME, ".config/notifications.conf")
_last_notify_time = 0


def _load_notify_config() -> dict:
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
            import configparser
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


def _should_notify(tool_name: str, result: str, config: dict) -> bool:
    """Determine if we should send auto-notification."""
    global _last_notify_time

    if not config["enabled"]:
        return False

    # Always notify on error
    if config["on_error"]:
        if result.startswith("Error") or "❌" in result or "⚠️" in result or "error" in result.lower()[:50]:
            return True

    # Cooldown check
    import time
    now = time.time()
    if now - _last_notify_time < config["cooldown"]:
        return False

    # Check include list (these ALWAYS notify)
    if tool_name in config["include_tools"]:
        return True

    # Check exclude list (these NEVER notify)
    if tool_name in config["exclude_tools"]:
        return False

    # Default: notify on execute
    return config["on_execute"]


def _send_auto_notification(tool_name: str, arguments: dict, result: str):
    """Send automatic notification after tool execution."""
    global _last_notify_time
    import time

    # Determine icon based on result content
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

    # Short message (first 150 chars, single line)
    msg = result[:150].replace("\n", " ").replace("\r", "")

    # Truncate with ellipsis if needed
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


def log_operation(tool: str, args: dict, result: str):
    try:
        with open(LOG_FILE, "a") as f:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            f.write(f"[{ts}] {tool}({json.dumps(args, ensure_ascii=False)}) → {result[:200]}\n")
    except Exception:
        pass


def is_blocked_command(cmd: str) -> bool:
    cmd_lower = cmd.lower().strip()
    for blocked in BLOCKED_COMMANDS:
        if blocked.lower() in cmd_lower:
            return True
    return False


def is_destructive_command(cmd: str) -> bool:
    cmd_lower = cmd.lower().strip()
    for pattern in DESTRUCTIVE_PATTERNS:
        if pattern in cmd_lower:
            return True
    return False


def safe_path(path: str) -> str:
    if not path:
        return BASE_DIR
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    return os.path.normpath(path)


def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_permissions(mode: int) -> str:
    perms = ""
    for who in ['USR', 'GRP', 'OTH']:
        r = 'r' if mode & getattr(__import__('stat'), f'S_I{who}READ') else '-'
        w = 'w' if mode & getattr(__import__('stat'), f'S_I{who}WRITE') else '-'
        x = 'x' if mode & getattr(__import__('stat'), f'S_I{who}EXEC') else '-'
        perms += r + w + x
    return perms


# ── Tool Definitions ──────────────────────────────────────
TOOLS = [
    {
        "name": "list_directory",
        "description": "Lista archivos y carpetas en un directorio. Retorna nombres, tamaños y tipo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del directorio. Default: home directory."
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Incluir archivos ocultos (que empiezan con .). Default: false."
                }
            },
            "required": []
        }
    },
    {
        "name": "file_info",
        "description": "Muestra metadata detallada de un archivo o carpeta: tamaño, permisos, fechas, tipo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo o carpeta."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_files",
        "description": "Busca archivos por nombre usando patrón glob (ej: '*.py', '**/*.txt').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Patrón de búsqueda glob."
                },
                "path": {
                    "type": "string",
                    "description": "Directorio base para buscar. Default: home."
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo de texto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a leer."
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Máximo de líneas a leer. Default: 200."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Escribe contenido a un archivo. Crea el archivo si no existe, sobreescribe si existe.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a escribir."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido a escribir."
                },
                "append": {
                    "type": "boolean",
                    "description": "Si es true, agrega al final en vez de sobreescribir. Default: false."
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "run_command",
        "description": "Ejecuta un comando del sistema y retorna su salida. Comandos destructivos requieren confirmación.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Comando a ejecutar (ej: 'ls -la', 'df -h', 'free -m')."
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Confirmar ejecución de comandos destructivos. Default: false."
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "get_system_info",
        "description": "Obtiene información del sistema: CPU, RAM, disco, OS, uptime.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "get_gpu_status",
        "description": "Obtiene estado de la GPU NVIDIA: VRAM, uso, temperatura, procesos.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "web_search",
        "description": "Busca en internet usando DuckDuckGo. Retorna resultados relevantes con títulos, URLs y snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados. Default: 5."
                },
                "region": {
                    "type": "string",
                    "description": "Región para búsqueda (ej: 'mx-es', 'us-en'). Default: 'wt-wt' (global)."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "open_url",
        "description": "Abre una URL en el navegador Brave.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL a abrir (ej: 'https://google.com')."
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "run_python_script",
        "description": "Ejecuta un script de Python y retorna la salida.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "Código Python a ejecutar."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos. Default: 30."
                }
            },
            "required": ["script"]
        }
    },
    {
        "name": "media_control",
        "description": "Controla reproducción de música: play, pause, next, previous, volume.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["play", "pause", "next", "previous", "volume_up", "volume_down", "mute", "get_status"],
                    "description": "Acción a ejecutar."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "send_notification",
        "description": "Envía una notificación de escritorio con opciones avanzadas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Título de la notificación."
                },
                "message": {
                    "type": "string",
                    "description": "Mensaje de la notificación."
                },
                "urgency": {
                    "type": "string",
                    "enum": ["low", "normal", "critical"],
                    "description": "Nivel de urgencia.",
                    "default": "normal"
                },
                "icon": {
                    "type": "string",
                    "description": "Ruta del icono o nombre stock (ej: dialog-information, weather-storm)."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en milisegundos (0 = no expira).",
                    "default": 5000
                },
                "category": {
                    "type": "string",
                    "description": "Categoría (ej: email, msg, transfer)."
                },
                "transient": {
                    "type": "boolean",
                    "description": "Notificación transitoria (desaparece rápido).",
                    "default": False
                }
            },
            "required": ["title", "message"]
        }
    },
    {
        "name": "spotify_search",
        "description": "Busca canciones, artistas o playlists en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda (canción, artista, playlist)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de resultados. Default: 5."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "spotify_now",
        "description": "Muestra qué canción está sonando ahora en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "spotify_play",
        "description": "Reanuda la reproducción en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "spotify_pause",
        "description": "Pausa la reproducción en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "spotify_next",
        "description": "Salta a la siguiente canción en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "spotify_previous",
        "description": "Va a la canción anterior en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "spotify_volume",
        "description": "Ajusta el volumen de Spotify (0-100).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "level": {
                    "type": "integer",
                    "description": "Nivel de volumen (0-100)."
                }
            },
            "required": ["level"]
        }
    },
    {
        "name": "spotify_playlists",
        "description": "Lista tus playlists de Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "spotify_launch",
        "description": "Abre Spotify si no está corriendo.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "spotify_play_track",
        "description": "Busca y reproduce una canción específica en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Nombre de la canción a reproducir."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "spotify_play_artist",
        "description": "Reproduce música de un artista en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artist": {
                    "type": "string",
                    "description": "Nombre del artista."
                }
            },
            "required": ["artist"]
        }
    },
    {
        "name": "spotify_play_playlist",
        "description": "Reproduce una playlist de Spotify por nombre.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre de la playlist."
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "delegate_to_subagent",
        "description": "Delega una tarea simple al sub-agente E4B (CPU). Útil para tools de Spotify, Kasa, info del sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Instrucción a delegar al sub-agente."
                }
            },
            "required": ["query"]
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
        "name": "clipboard",
        "description": "Copia o pega texto del clipboard del sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["copy", "paste", "clear"],
                    "description": "Acción: copy (copiar), paste (pegar), clear (limpiar)."
                },
                "text": {
                    "type": "string",
                    "description": "Texto a copiar (requerido para action=copy)."
                }
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
                "action": {
                    "type": "string",
                    "enum": ["get", "set", "up", "down"],
                    "description": "Acción: get (obtener), set (establecer), up (subir), down (bajar)."
                },
                "level": {
                    "type": "integer",
                    "description": "Nivel de brillo (0-100) para action=set."
                }
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
                "city": {
                    "type": "string",
                    "description": "Nombre de la ciudad (ej: 'Ciudad de Mexico', 'Madrid'). Default: ubicación automática."
                }
            },
            "required": []
        }
    },
    {
        "name": "timer",
        "description": "Crea un temporizador o alarma. Notifica cuando termina.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "minutes": {
                    "type": "integer",
                    "description": "Duración en minutos."
                },
                "message": {
                    "type": "string",
                    "description": "Mensaje de notificación cuando termine."
                }
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
                "action": {
                    "type": "string",
                    "enum": ["create", "list", "read", "delete"],
                    "description": "Acción a ejecutar."
                },
                "title": {
                    "type": "string",
                    "description": "Título de la nota."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido de la nota (para create)."
                },
                "category": {
                    "type": "string",
                    "enum": ["General", "Trabajo", "Personal", "Tasks"],
                    "description": "Categoría de la nota. Default: General."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "memory_save",
        "description": "Guarda información en la memoria persistente del asistente.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["note", "fact", "preference", "context", "task"],
                    "description": "Categoría de la entrada."
                },
                "title": {
                    "type": "string",
                    "description": "Título o resumen corto."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido completo de la entrada."
                },
                "tags": {
                    "type": "string",
                    "description": "Tags separados por comas (ej: 'spotify,música,favorito')."
                }
            },
            "required": ["category", "content"]
        }
    },
    {
        "name": "memory_search",
        "description": "Busca en la memoria persistente por texto o tags.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Texto a buscar en contenido o tags."
                },
                "category": {
                    "type": "string",
                    "enum": ["note", "fact", "preference", "context", "task"],
                    "description": "Filtrar por categoría (opcional)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de resultados. Default: 10."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_context",
        "description": "Obtiene las entradas más recientes de memoria para dar contexto al modelo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": ["note", "fact", "preference", "context", "task"],
                    "description": "Filtrar por categoría (opcional)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de entradas. Default: 5."
                }
            },
            "required": []
        }
    },
    {
        "name": "memory_list",
        "description": "Lista todas las entradas de memoria recientes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Máximo de entradas. Default: 20."
                }
            },
            "required": []
        }
    },
    {
        "name": "memory_delete",
        "description": "Elimina una entrada de memoria por ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {
                    "type": "integer",
                    "description": "ID de la entrada a eliminar."
                }
            },
            "required": ["id"]
        }
    },
    {
        "name": "system_shutdown",
        "description": "Apaga o reinicia el sistema. REQUIERE CONFIRMACIÓN.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["shutdown", "reboot", "suspend", "hibernate"],
                    "description": "Acción del sistema."
                },
                "delay": {
                    "type": "integer",
                    "description": "Delay en segundos (default: 0 = inmediato)."
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Confirmar acción destructiva."
                }
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_compress",
        "description": "Comprime archivos o carpetas en .tar.gz o .zip.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Ruta del archivo o carpeta a comprimir."
                },
                "format": {
                    "type": "string",
                    "enum": ["tar.gz", "zip"],
                    "description": "Formato de compresión. Default: tar.gz."
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "file_extract",
        "description": "Extrae archivos comprimidos (.tar.gz, .zip, .tar.bz2).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Ruta del archivo a extraer."
                },
                "destination": {
                    "type": "string",
                    "description": "Directorio destino. Default: directorio actual."
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "file_permissions",
        "description": "Cambia permisos de archivos o carpetas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo."
                },
                "mode": {
                    "type": "string",
                    "description": "Permisos en formato octal (ej: '755') o simbólico (ej: '+x')."
                }
            },
            "required": ["path", "mode"]
        }
    },
    {
        "name": "network_ping",
        "description": "Hace ping a un host para verificar conectividad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o IP a hacer ping."
                },
                "count": {
                    "type": "integer",
                    "description": "Número de paquetes. Default: 4."
                }
            },
            "required": ["host"]
        }
    },
    {
        "name": "network_ports",
        "description": "Muestra puertos abiertos en el sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Filtrar por estado (LISTEN, ESTABLISHED, etc.)."
                }
            },
            "required": []
        }
    },
    {
        "name": "network_speed",
        "description": "Mide la velocidad de internet (upload/download).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "network_info",
        "description": "Muestra información de red: interfaces, IPs, gateway, DNS.",
        "inputSchema": {
            "type": "object",
            "properties": {}
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
        "name": "audio_list_devices",
        "description": "Lista dispositivos de audio del sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "audio_set_source",
        "description": "Cambia la fuente de audio (sink).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sink": {
                    "type": "string",
                    "description": "Nombre del sink (dispositivo de salida)."
                }
            },
            "required": ["sink"]
        }
    },
    {
        "name": "audio_set_source_input",
        "description": "Cambia la fuente de entrada de audio (source).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Nombre del source (dispositivo de entrada)."
                }
            },
            "required": ["source"]
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
    {
        "name": "gh_repos_list",
        "description": "Lista repositorios de GitHub del usuario.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Número de repos. Default: 20."
                },
                "visibility": {
                    "type": "string",
                    "enum": ["all", "public", "private"],
                    "description": "Visibilidad. Default: all."
                }
            },
            "required": []
        }
    },
    {
        "name": "gh_repo_info",
        "description": "Muestra información detallada de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Nombre del repositorio (owner/repo o solo repo)."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_repo_create",
        "description": "Crea un nuevo repositorio en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre del repositorio."
                },
                "description": {
                    "type": "string",
                    "description": "Descripción del repositorio."
                },
                "private": {
                    "type": "boolean",
                    "description": "Si es privado. Default: false."
                },
                "auto_init": {
                    "type": "boolean",
                    "description": "Inicializar con README. Default: true."
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "gh_issues_list",
        "description": "Lista issues de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Estado. Default: open."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de issues. Default: 20."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_issue_create",
        "description": "Crea un issue en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "title": {
                    "type": "string",
                    "description": "Título del issue."
                },
                "body": {
                    "type": "string",
                    "description": "Contenido del issue."
                },
                "labels": {
                    "type": "string",
                    "description": "Labels separados por coma."
                }
            },
            "required": ["repo", "title"]
        }
    },
    {
        "name": "gh_pr_list",
        "description": "Lista pull requests de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Estado. Default: open."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de PRs. Default: 20."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_pr_create",
        "description": "Crea un pull request en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "title": {
                    "type": "string",
                    "description": "Título del PR."
                },
                "body": {
                    "type": "string",
                    "description": "Descripción del PR."
                },
                "head": {
                    "type": "string",
                    "description": "Branch origen."
                },
                "base": {
                    "type": "string",
                    "description": "Branch destino. Default: main."
                }
            },
            "required": ["repo", "title", "head"]
        }
    },
    {
        "name": "gh_pr_merge",
        "description": "Merge un pull request.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "pr_number": {
                    "type": "integer",
                    "description": "Número del PR."
                }
            },
            "required": ["repo", "pr_number"]
        }
    },
    {
        "name": "gh_actions_list",
        "description": "Lista GitHub Actions workflows de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_actions_runs",
        "description": "Muestra ejecuciones recientes de GitHub Actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de runs. Default: 10."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_release_list",
        "description": "Lista releases de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de releases. Default: 10."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_gist_list",
        "description": "Lista tus Gists de GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Número de gists. Default: 20."
                }
            },
            "required": []
        }
    },
    {
        "name": "gh_gist_create",
        "description": "Crea un Gist en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre del archivo."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido del archivo."
                },
                "description": {
                    "type": "string",
                    "description": "Descripción del Gist."
                },
                "public": {
                    "type": "boolean",
                    "description": "Si es público. Default: false."
                }
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "gh_search_repos",
        "description": "Busca repositorios en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de resultados. Default: 10."
                },
                "language": {
                    "type": "string",
                    "description": "Filtrar por lenguaje."
                },
                "sort": {
                    "type": "string",
                    "enum": ["stars", "forks", "updated"],
                    "description": "Ordenar por. Default: stars."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "gh_search_code",
        "description": "Busca código en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "repo": {
                    "type": "string",
                    "description": "Filtrar por repositorio (owner/repo)."
                },
                "language": {
                    "type": "string",
                    "description": "Filtrar por lenguaje."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de resultados. Default: 10."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "git_status",
        "description": "Muestra el estado del repositorio Git actual.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio. Default: directorio actual."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_log",
        "description": "Muestra el historial de commits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número de commits. Default: 10."
                },
                "branch": {
                    "type": "string",
                    "description": "Branch a mostrar. Default: actual."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_diff",
        "description": "Muestra diferencias en el repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                },
                "file": {
                    "type": "string",
                    "description": "Archivo específico a comparar."
                },
                "staged": {
                    "type": "boolean",
                    "description": "Mostrar cambios staged. Default: false."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_branches",
        "description": "Lista branches del repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_commit",
        "description": "Crea un commit con cambios staged.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                },
                "message": {
                    "type": "string",
                    "description": "Mensaje del commit."
                },
                "add_all": {
                    "type": "boolean",
                    "description": "Agregar todos los cambios (git add -A). Default: false."
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "git_push",
        "description": "Push commits al remote.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                },
                "branch": {
                    "type": "string",
                    "description": "Branch a push. Default: actual."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_pull",
        "description": "Pull cambios del remote.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_clone",
        "description": "Clona un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL del repositorio a clonar."
                },
                "destination": {
                    "type": "string",
                    "description": "Directorio destino."
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "code_analyze",
        "description": "Analiza un archivo de código y muestra estadísticas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a analizar."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "code_count_lines",
        "description": "Cuenta líneas de código en un directorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del directorio."
                },
                "extension": {
                    "type": "string",
                    "description": "Extensión a filtrar (ej: 'py', 'js')."
                }
            },
            "required": []
        }
    },
    {
        "name": "code_search_pattern",
        "description": "Busca un patrón en archivos de código.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Patrón regex a buscar."
                },
                "path": {
                    "type": "string",
                    "description": "Directorio a buscar."
                },
                "extension": {
                    "type": "string",
                    "description": "Extensión de archivo."
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "project_dependencies",
        "description": "Muestra dependencias de un proyecto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del proyecto."
                }
            },
            "required": []
        }
    },
    {
        "name": "project_structure",
        "description": "Muestra la estructura de un proyecto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del proyecto."
                },
                "depth": {
                    "type": "integer",
                    "description": "Profundidad máxima. Default: 3."
                }
            },
            "required": []
        }
    },
    {
        "name": "docker_ps",
        "description": "Muestra contenedores Docker activos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "all": {
                    "type": "boolean",
                    "description": "Mostrar todos (incluyendo detenidos). Default: false."
                }
            },
            "required": []
        }
    },
    {
        "name": "docker_logs",
        "description": "Muestra logs de un contenedor Docker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "container": {
                    "type": "string",
                    "description": "Nombre o ID del contenedor."
                },
                "lines": {
                    "type": "integer",
                    "description": "Número de líneas. Default: 50."
                }
            },
            "required": ["container"]
        }
    },
    {
        "name": "docker_images",
        "description": "Muestra imágenes Docker disponibles.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "chat_export",
        "description": "Exporta una conversación y genera enlace para compartir con QR.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "string",
                    "description": "Mensajes en formato JSON: [{\"role\":\"user\",\"content\":\"...\"},...]"
                },
                "title": {
                    "type": "string",
                    "description": "Título del chat (opcional)."
                }
            },
            "required": ["messages"]
        }
    },
    {
        "name": "chat_list_shared",
        "description": "Lista todos los chats exportados/compartidos.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "chat_get_shared",
        "description": "Obtiene un chat compartido por su ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": "string",
                    "description": "ID del chat compartido."
                }
            },
            "required": ["chat_id"]
        }
    },
    # ── Email Tools ─────────────────────────────────────────
    {
        "name": "email_send",
        "description": "Envía un correo electrónico usando msmtp. Requiere configuración previa en ~/.msmtprc o en la tabla access_credentials.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Destinatario del correo."
                },
                "subject": {
                    "type": "string",
                    "description": "Asunto del correo."
                },
                "body": {
                    "type": "string",
                    "description": "Cuerpo del correo (texto plano o HTML)."
                },
                "cc": {
                    "type": "string",
                    "description": "CC (opcional)."
                },
                "bcc": {
                    "type": "string",
                    "description": "BCC (opcional)."
                },
                "html": {
                    "type": "boolean",
                    "description": "Si el cuerpo es HTML.",
                    "default": False
                },
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Rutas de archivos adjuntos (opcional)."
                }
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "email_configure",
        "description": "Configura msmtp con credenciales SMTP. Guarda en ~/.msmtprc y en la DB.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "smtp_host": {
                    "type": "string",
                    "description": "Servidor SMTP (ej: smtp.gmail.com)."
                },
                "smtp_port": {
                    "type": "integer",
                    "description": "Puerto SMTP.",
                    "default": 587
                },
                "username": {
                    "type": "string",
                    "description": "Usuario SMTP."
                },
                "password": {
                    "type": "string",
                    "description": "Contraseña SMTP."
                },
                "from_name": {
                    "type": "string",
                    "description": "Nombre del remitente."
                },
                "from_email": {
                    "type": "string",
                    "description": "Email del remitente."
                },
                "tls": {
                    "type": "boolean",
                    "description": "Usar TLS.",
                    "default": True
                }
            },
            "required": ["smtp_host", "username", "password", "from_email"]
        }
    },
    {
        "name": "email_test",
        "description": "Envía un correo de prueba para verificar la configuración SMTP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Email de prueba (default: remitente)."
                }
            }
        }
    },
    # ── SSH Tools ───────────────────────────────────────────
    {
        "name": "ssh_connect",
        "description": "Ejecuta un comando en un servidor remoto vía SSH.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH (ej: vps, 192.168.1.100)."
                },
                "command": {
                    "type": "string",
                    "description": "Comando a ejecutar remotamente."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH (default: darkseid)."
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos.",
                    "default": 30
                }
            },
            "required": ["host", "command"]
        }
    },
    {
        "name": "ssh_copy",
        "description": "Copia archivos al servidor remoto vía SCP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH."
                },
                "local_path": {
                    "type": "string",
                    "description": "Ruta local del archivo."
                },
                "remote_path": {
                    "type": "string",
                    "description": "Ruta remota de destino."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH."
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                }
            },
            "required": ["host", "local_path", "remote_path"]
        }
    },
    {
        "name": "ssh_fetch",
        "description": "Descarga archivos del servidor remoto vía SCP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH."
                },
                "remote_path": {
                    "type": "string",
                    "description": "Ruta remota del archivo."
                },
                "local_path": {
                    "type": "string",
                    "description": "Ruta local de destino."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH."
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                }
            },
            "required": ["host", "remote_path", "local_path"]
        }
    },
    {
        "name": "ssh_sync",
        "description": "Sincroniza directorios locales con remoto vía rsync.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH."
                },
                "local_path": {
                    "type": "string",
                    "description": "Ruta local."
                },
                "remote_path": {
                    "type": "string",
                    "description": "Ruta remota."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH."
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                },
                "delete": {
                    "type": "boolean",
                    "description": "Eliminar archivos en remoto que no existen local.",
                    "default": False
                },
                "exclude": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Patrones a excluir."
                }
            },
            "required": ["host", "local_path", "remote_path"]
        }
    },
    {
        "name": "ssh_tunnel",
        "description": "Crea un túnel SSH con autossh para port forwarding.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host remoto."
                },
                "local_port": {
                    "type": "integer",
                    "description": "Puerto local."
                },
                "remote_port": {
                    "type": "integer",
                    "description": "Puerto remoto."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH."
                },
                "ssh_port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                },
                "background": {
                    "type": "boolean",
                    "description": "Ejecutar en segundo plano.",
                    "default": True
                }
            },
            "required": ["host", "local_port", "remote_port"]
        }
    },
    {
        "name": "ssh_list_hosts",
        "description": "Lista hosts configurados en ~/.ssh/config.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "ssh_add_host",
        "description": "Agrega un host a ~/.ssh/config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hostname": {
                    "type": "string",
                    "description": "Alias del host (ej: vps)."
                },
                "host": {
                    "type": "string",
                    "description": "IP o dominio del servidor."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH.",
                    "default": "darkseid"
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                },
                "identity_file": {
                    "type": "string",
                    "description": "Ruta de la clave SSH (opcional)."
                }
            },
            "required": ["hostname", "host"]
        }
    },
    {
        "name": "ssh_status",
        "description": "Verifica estado de un servidor remoto (ping + SSH).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH."
                }
            },
            "required": ["host"]
        }
    },
    # ── Communication Tools ────────────────────────────────
    {
        "name": "email_discover_settings",
        "description": "Auto-descubre configuración SMTP para un dominio. Busca MX records y prueba puertos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email completo (ej: user@gmail.com) o dominio (gmail.com)."
                }
            },
            "required": ["email"]
        }
    },
    {
        "name": "email_setup_wizard",
        "description": "Wizard completo: descubre SMTP, configura msmtp, guarda en DB encriptado, y prueba conexión.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email completo (ej: user@gmail.com)."
                },
                "password": {
                    "type": "string",
                    "description": "Contraseña o App Password."
                },
                "display_name": {
                    "type": "string",
                    "description": "Nombre para mostrar (opcional)."
                }
            },
            "required": ["email", "password"]
        }
    },
    {
        "name": "format_whatsapp",
        "description": "Formatea texto para WhatsApp con emojis, negritas, listas anidadas y elementos rich text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "elements": {
                    "type": "array",
                    "description": "Array de elementos a formatear.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["heading", "bold", "italic", "strikethrough", "code", "text", "list", "emoji", "link", "newline", "divider"]},
                            "text": {"type": "string"},
                            "items": {"type": "array", "items": {"type": "object"}},
                            "url": {"type": "string"},
                            "name": {"type": "string"}
                        },
                        "required": ["type"]
                    }
                },
                "copy_to_clipboard": {
                    "type": "boolean",
                    "description": "Copiar resultado al clipboard.",
                    "default": True
                }
            },
            "required": ["elements"]
        }
    },
    {
        "name": "whatsapp_link",
        "description": "Genera enlace de WhatsApp con mensaje prellenado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Número de teléfono con código país (ej: 521234567890)."
                },
                "message": {
                    "type": "string",
                    "description": "Mensaje prellenado."
                },
                "copy_to_clipboard": {
                    "type": "boolean",
                    "description": "Copiar enlace al clipboard.",
                    "default": True
                }
            },
            "required": ["phone", "message"]
        }
    },
    {
        "name": "format_email",
        "description": "Compone cuerpo de email con formato (plain text, HTML, o ambos).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Nombre del destinatario (para saludo)."
                },
                "subject": {
                    "type": "string",
                    "description": "Asunto del correo."
                },
                "greeting": {
                    "type": "string",
                    "description": "Saludo personalizado (default: 'Hola {to},')."
                },
                "body": {
                    "type": "string",
                    "description": "Cuerpo principal del correo."
                },
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de puntos a incluir."
                },
                "signature": {
                    "type": "string",
                    "description": "Firma del correo."
                },
                "format": {
                    "type": "string",
                    "enum": ["plain", "html", "both"],
                    "description": "Formato de salida.",
                    "default": "both"
                },
                "copy_to_clipboard": {
                    "type": "boolean",
                    "description": "Copiar resultado al clipboard.",
                    "default": False
                }
            },
            "required": ["body"]
        }
    },
    # ── Web & Internet Tools ────────────────────────────────
    {
        "name": "browse_web",
        "description": "Obtiene contenido de una URL. Retorna texto, HTML, o JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL a obtener."
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "html", "json"],
                    "description": "Formato de salida.",
                    "default": "text"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos.",
                    "default": 30
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "http_request",
        "description": "Realiza petición HTTP (GET, POST, PUT, DELETE, PATCH).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL del endpoint."
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "description": "Método HTTP.",
                    "default": "GET"
                },
                "headers": {
                    "type": "object",
                    "description": "Headers HTTP."
                },
                "body": {
                    "type": "string",
                    "description": "Body de la petición (JSON o texto)."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos.",
                    "default": 30
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "search_news",
        "description": "Busca noticias recientes en DuckDuckGo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "region": {
                    "type": "string",
                    "description": "Región (ej: mx-mx, us-en).",
                    "default": "wt-wt"
                },
                "time": {
                    "type": "string",
                    "enum": ["d", "w", "m", "y"],
                    "description": "Período: día, semana, mes, año.",
                    "default": "w"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados.",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_docs",
        "description": "Busca documentación técnica (Stack Overflow, GitHub, MDN, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "language": {
                    "type": "string",
                    "description": "Lenguaje de programación (ej: python, javascript)."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados.",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "dns_lookup",
        "description": "Consulta DNS (A, AAAA, MX, TXT, NS, CNAME).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Dominio a consultar."
                },
                "record_type": {
                    "type": "string",
                    "enum": ["A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA", "ALL"],
                    "description": "Tipo de registro.",
                    "default": "ALL"
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "ssl_check",
        "description": "Verifica certificado SSL de un dominio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Dominio a verificar."
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "whois_lookup",
        "description": "Consulta WHOIS de un dominio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Dominio a consultar."
                }
            },
            "required": ["domain"]
        }
    },
    # ── Database Tools ──────────────────────────────────────
    {
        "name": "sql_query",
        "description": "Ejecuta query SQL en una base de datos SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Ruta de la DB SQLite (default: ai-memory.db)."
                },
                "query": {
                    "type": "string",
                    "description": "Query SQL a ejecutar."
                },
                "params": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Parámetros de la query."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "backup_database",
        "description": "Crea backup de una base de datos SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Ruta de la DB a respaldar."
                },
                "backup_path": {
                    "type": "string",
                    "description": "Ruta del backup (default: auto-generada)."
                }
            },
            "required": ["database"]
        }
    },
    # ── Data Processing Tools ───────────────────────────────
    {
        "name": "csv_to_json",
        "description": "Convierte CSV a JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Ruta del archivo CSV."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida JSON (opcional)."
                }
            },
            "required": ["input_file"]
        }
    },
    {
        "name": "json_to_csv",
        "description": "Convierte JSON a CSV.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Ruta del archivo JSON."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida CSV (opcional)."
                }
            },
            "required": ["input_file"]
        }
    },
    {
        "name": "convert_file",
        "description": "Convierte entre formatos: CSV, JSON, XML, YAML, Markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Ruta del archivo de entrada."
                },
                "output_format": {
                    "type": "string",
                    "enum": ["csv", "json", "xml", "yaml", "md", "txt"],
                    "description": "Formato de salida."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida (opcional)."
                }
            },
            "required": ["input_file", "output_format"]
        }
    },
    {
        "name": "extract_pdf",
        "description": "Extrae texto de un archivo PDF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Ruta del PDF."
                },
                "pages": {
                    "type": "string",
                    "description": "Páginas a extraer (ej: '1-5', '1,3,5', 'all').",
                    "default": "all"
                }
            },
            "required": ["pdf_path"]
        }
    },
    {
        "name": "generate_csv",
        "description": "Genera archivo CSV desde datos estructurados.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Datos en formato JSON (array de objetos)."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida."
                },
                "delimiter": {
                    "type": "string",
                    "description": "Delimitador.",
                    "default": ","
                }
            },
            "required": ["data", "output_file"]
        }
    },
    {
        "name": "data_analysis",
        "description": "Análisis básico de datos: estadísticas, valores únicos, nulos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Ruta del archivo (CSV o JSON)."
                },
                "column": {
                    "type": "string",
                    "description": "Columna específica a analizar."
                }
            },
            "required": ["file_path"]
        }
    },
    # ── Log & System Tools ──────────────────────────────────
    {
        "name": "log_analysis",
        "description": "Analiza logs del sistema: errores, warnings, patrones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "log_file": {
                    "type": "string",
                    "description": "Ruta del archivo de log."
                },
                "lines": {
                    "type": "integer",
                    "description": "Últimas N líneas a analizar.",
                    "default": 100
                },
                "filter": {
                    "type": "string",
                    "description": "Filtrar por nivel (ERROR, WARN, INFO)."
                }
            },
            "required": ["log_file"]
        }
    },
    {
        "name": "generate_report",
        "description": "Genera reporte en Markdown con datos y análisis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Título del reporte."
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"},
                            "data": {"type": "array"}
                        }
                    },
                    "description": "Secciones del reporte."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida (opcional)."
                }
            },
            "required": ["title", "sections"]
        }
    },
    # ── Security Tools ──────────────────────────────────────
    {
        "name": "security_audit",
        "description": "Auditoría básica de seguridad: permisos, puertos abiertos, usuarios.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["full", "ports", "files", "users"],
                    "description": "Alcance de la auditoría.",
                    "default": "full"
                }
            }
        }
    },
    {
        "name": "secret_detection",
        "description": "Detecta posibles secretos/claves en archivos de código.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directorio a escanear."
                },
                "extensions": {
                    "type": "string",
                    "description": "Extensiones a escanear (ej: '.py,.js,.env').",
                    "default": ".py,.js,.ts,.env,.json,.yaml,.yml,.cfg,.conf"
                }
            }
        }
    },
    # ── Task & Planning Tools ───────────────────────────────
    {
        "name": "plan_tasks",
        "description": "Genera plan de tareas para un objetivo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "Objetivo a planificar."
                },
                "context": {
                    "type": "string",
                    "description": "Contexto adicional."
                },
                "max_tasks": {
                    "type": "integer",
                    "description": "Máximo de tareas.",
                    "default": 10
                }
            },
            "required": ["objective"]
        }
    },
    # ── Enhanced Communication Tools ────────────────────────
    {
        "name": "notify_contextual",
        "description": "Notificación contextual: la IA notifica cuando completa una tarea. Usa esto cuando termines de hacer algo importante.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Nombre de la tarea completada (ej: 'Envío de correo', 'Backup de DB')."
                },
                "result": {
                    "type": "string",
                    "description": "Resultado breve de la tarea."
                },
                "importance": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Importancia de la notificación.",
                    "default": "medium"
                },
                "icon": {
                    "type": "string",
                    "description": "Icono (ej: mail-send, document-save, dialog-information)."
                }
            },
            "required": ["task", "result"]
        }
    },
    # ── Enhanced Search Tools ───────────────────────────────
    {
        "name": "search_google",
        "description": "Búsqueda en Google con soporte para AI Mode. Mejor que DuckDuckGo para noticias y eventos recientes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados.",
                    "default": 10
                },
                "language": {
                    "type": "string",
                    "description": "Idioma (es, en, etc.).",
                    "default": "es"
                },
                "region": {
                    "type": "string",
                    "description": "Región (mx, us, etc.).",
                    "default": "mx"
                },
                "time_filter": {
                    "type": "string",
                    "enum": ["hour", "day", "week", "month", "year"],
                    "description": "Filtrar por tiempo."
                },
                "site": {
                    "type": "string",
                    "description": "Sitio específico (ej: espn.com, marca.com)."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_sports",
        "description": "Búsqueda de resultados deportivos en vivo. Fútbol,篮球, tenis, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Búsqueda (ej: 'Real Madrid vs Barcelona', 'Liga MX resultados')."
                },
                "sport": {
                    "type": "string",
                    "enum": ["football", "basketball", "tennis", "f1", "mma", "other"],
                    "description": "Tipo de deporte.",
                    "default": "football"
                },
                "live": {
                    "type": "boolean",
                    "description": "Buscar solo partidos en vivo.",
                    "default": False
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch_article",
        "description": "Obtiene contenido completo de un artículo web usando BeautifulSoup. Limpia HTML y retorna texto limpio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL del artículo."
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Máximo de caracteres.",
                    "default": 5000
                },
                "extract_links": {
                    "type": "boolean",
                    "description": "Incluir enlaces encontrados.",
                    "default": False
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "search_with_content",
        "description": "Busca en Google y obtiene el contenido completo del primer resultado. Ideal para respuestas rápidas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Máximo de caracteres del contenido.",
                    "default": 3000
                },
                "site": {
                    "type": "string",
                    "description": "Sitio específico."
                }
            },
            "required": ["query"]
        }
    },
    # ── OSINT Tools ─────────────────────────────────────────
    {
        "name": "osint_username",
        "description": "Búsqueda OSINT de username en 3000+ plataformas (maigret/sherlock). Encuentra cuentas en redes sociales, foros, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "Username a buscar (ej: dantecc10)."
                },
                "sites": {
                    "type": "string",
                    "description": "Sitios específicos separados por coma (ej: github,instagram,twitter)."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados a mostrar.",
                    "default": 50
                }
            },
            "required": ["username"]
        }
    },
    {
        "name": "osint_email",
        "description": "Investiga un email para encontrar cuentas asociadas en redes sociales y plataformas (holehe).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email a investigar."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados.",
                    "default": 30
                }
            },
            "required": ["email"]
        }
    },
    {
        "name": "osint_domain",
        "description": "Inteligencia de dominio: registros DNS, WHOIS, subdominios, conectividad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Dominio a investigar (ej: example.com)."
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "osint_ip",
        "description": "Inteligencia de IP: geolocalización, ASN, reverse DNS, puertos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ip_address": {
                    "type": "string",
                    "description": "Dirección IP a investigar."
                }
            },
            "required": ["ip_address"]
        }
    },
    {
        "name": "osint_person",
        "description": "Busca una persona por nombre en múltiples plataformas. Genera variaciones de username.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre completo de la persona."
                },
                "email": {
                    "type": "string",
                    "description": "Email conocido (opcional, mejora la búsqueda)."
                },
                "location": {
                    "type": "string",
                    "description": "Ubicación conocida (opcional)."
                }
            },
            "required": ["name"]
        }
    }
]


# ── Tool Implementations ──────────────────────────────────
def tool_list_directory(path: str = None, show_hidden: bool = False) -> str:
    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: Directorio no existe: {target}"
    if not os.path.isdir(target):
        return f"Error: No es un directorio: {target}"

    entries = []
    try:
        for name in sorted(os.listdir(target)):
            if not show_hidden and name.startswith("."):
                continue
            full_path = os.path.join(target, name)
            try:
                stat = os.lstat(full_path)
                is_dir = os.path.isdir(full_path)
                size = stat.st_size if not is_dir else 0
                entries.append({
                    "name": name + ("/" if is_dir else ""),
                    "type": "dir" if is_dir else "file",
                    "size": format_size(size) if not is_dir else "-"
                })
            except OSError:
                entries.append({"name": name, "type": "unknown", "size": "?"})
    except PermissionError:
        return f"Error: Sin permisos para leer: {target}"

    if not entries:
        return f"Directorio vacío: {target}"

    lines = [f"📁 {target} ({len(entries)} elementos)\n"]
    for e in entries:
        icon = "📁" if e["type"] == "dir" else "📄"
        lines.append(f"  {icon} {e['name']:40s} {e['size']}")

    return "\n".join(lines)


def tool_file_info(path: str) -> str:
    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: No existe: {target}"

    try:
        stat = os.lstat(target)
        import stat as stat_mod

        is_dir = os.path.isdir(target)
        is_link = os.path.islink(target)
        size = stat.st_size
        perms = format_permissions(stat.st_mode)
        modified = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        created = datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")

        file_type = "Directorio" if is_dir else "Enlace" if is_link else "Archivo"

        lines = [
            f"📄 {target}",
            f"  Tipo:      {file_type}",
            f"  Tamaño:    {format_size(size)}",
            f"  Permisos:  {perms}",
            f"  Modificado:{modified}",
            f"  Creado:    {created}",
        ]

        if is_dir:
            try:
                count = len(os.listdir(target))
                lines.append(f"  Contenido: {count} elementos")
            except PermissionError:
                lines.append(f"  Contenido: Sin permisos")

        if is_link:
            lines.append(f"  Target:    {os.readlink(target)}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error obteniendo info: {e}"


def tool_search_files(pattern: str, path: str = None) -> str:
    base = safe_path(path)
    if not os.path.isdir(base):
        return f"Error: Directorio no existe: {base}"

    try:
        search_pattern = os.path.join(base, "**", pattern)
        matches = glob.glob(search_pattern, recursive=True)

        if not matches:
            return f"No se encontraron archivos con patrón '{pattern}' en {base}"

        lines = [f"🔍 Resultados para '{pattern}' ({len(matches)} archivos):\n"]
        for match in sorted(matches)[:50]:
            rel = os.path.relpath(match, base)
            try:
                size = format_size(os.path.getsize(match))
            except OSError:
                size = "?"
            lines.append(f"  📄 {rel} ({size})")

        if len(matches) > 50:
            lines.append(f"\n  ... y {len(matches) - 50} más")

        return "\n".join(lines)
    except Exception as e:
        return f"Error en búsqueda: {e}"


def tool_read_file(path: str, max_lines: int = 200) -> str:
    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: No existe: {target}"
    if os.path.isdir(target):
        return f"Error: Es un directorio, no un archivo: {target}"

    try:
        file_size = os.path.getsize(target)
        if file_size > MAX_FILE_SIZE:
            return f"Error: Archivo demasiado grande ({format_size(file_size)}). Máximo: {format_size(MAX_FILE_SIZE)}"

        with open(target, "r", errors="replace") as f:
            lines = []
            for i, line in enumerate(f):
                if i >= max_lines:
                    lines.append(f"\n... (truncado, {max_lines} líneas mostradas)")
                    break
                lines.append(line.rstrip())

        return "\n".join(lines)
    except Exception as e:
        return f"Error leyendo archivo: {e}"


def tool_write_file(path: str, content: str, append: bool = False) -> str:
    target = safe_path(path)

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)

        mode = "a" if append else "w"
        with open(target, mode) as f:
            f.write(content)

        action = "agregado" if append else "escrito"
        size = os.path.getsize(target)
        log_operation("write_file", {"path": path, "append": append}, f"{action} {format_size(size)}")
        return f"✅ Archivo {action}: {target} ({format_size(size)})"
    except Exception as e:
        return f"Error escribiendo archivo: {e}"


def tool_run_command(command: str, confirm: bool = False) -> str:
    if is_blocked_command(command):
        return f"❌ Comando bloqueado por seguridad: {command}"

    if is_destructive_command(command) and not confirm:
        return (
            f"⚠️ Comando destructivo detectado: {command}\n"
            f"Para ejecutar, responde al LLM con confirmación.\n"
            f"El LLM llamará de nuevo con confirm=true."
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            env={**os.environ, "TERM": "dumb"}
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        lines = output.strip().split("\n")
        if len(lines) > MAX_OUTPUT_LINES:
            output = "\n".join(lines[:MAX_OUTPUT_LINES]) + f"\n... ({len(lines)} líneas totales, truncado)"

        log_operation("run_command", {"command": command}, f"exit={result.returncode}")

        if result.returncode != 0:
            return f"⚠️ Comando terminó con código {result.returncode}:\n{output}"
        return output if output else "(sin salida)"

    except subprocess.TimeoutExpired:
        return f"⏰ Comando excedió timeout de {COMMAND_TIMEOUT}s: {command}"
    except Exception as e:
        return f"Error ejecutando comando: {e}"


def tool_get_system_info() -> str:
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
        cores = os.cpu_count()
        info.append(f"Cores: {cores}")
    except Exception:
        pass

    try:
        result = subprocess.run(["free", "-m"], capture_output=True, text=True, timeout=5)
        for line in result.stdout.split("\n"):
            if line.startswith("Mem:"):
                parts = line.split()
                total = int(parts[1])
                used = int(parts[2])
                free = int(parts[3])
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


def tool_get_gpu_status() -> str:
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
                name = parts[0]
                vram_used = parts[1]
                vram_total = parts[2]
                temp = parts[3]
                gpu_util = parts[4]
                mem_util = parts[5]
                power = parts[6]

                info.append(f"  GPU {i}: {name}")
                info.append(f"  VRAM: {vram_used}MB / {vram_total}MB")
                info.append(f"  Temperatura: {temp}°C")
                info.append(f"  Uso GPU: {gpu_util}%")
                info.append(f"  Uso Memoria: {mem_util}%")
                info.append(f"  Consumo: {power}W")

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


def tool_web_search(query: str, max_results: int = 5, region: str = "wt-wt") -> str:
    try:
        from duckduckgo_search import DDGS

        with DDGS() as ddgs:
            results = list(ddgs.text(query, region=region, max_results=max_results))

        if not results:
            return f"No se encontraron resultados para: {query}"

        lines = [f"🔍 Resultados para '{query}' ({len(results)} resultados):\n"]

        for i, r in enumerate(results, 1):
            title = r.get("title", "Sin título")
            url = r.get("href", r.get("link", ""))
            snippet = r.get("body", r.get("snippet", ""))[:200]

            lines.append(f"  {i}. {title}")
            lines.append(f"     URL: {url}")
            if snippet:
                lines.append(f"     {snippet}")
            lines.append("")

        log_operation("web_search", {"query": query}, f"{len(results)} results")
        return "\n".join(lines)

    except ImportError:
        return "Error: duckduckgo-search no instalado. Ejecuta: pip install duckduckgo-search"
    except Exception as e:
        return f"Error en búsqueda: {e}"


def tool_open_url(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        subprocess.Popen(
            ["brave-browser", "--new-tab", url],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        log_operation("open_url", {"url": url}, "opened")
        return f"🌐 Abriendo: {url}"
    except Exception as e:
        return f"Error abriendo URL: {e}"


def tool_run_python_script(script: str, timeout: int = 30) -> str:
    if is_blocked_command(script):
        return "❌ Script bloqueado por seguridad"

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=HOME
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        lines = output.strip().split("\n")
        if len(lines) > MAX_OUTPUT_LINES:
            output = "\n".join(lines[:MAX_OUTPUT_LINES]) + f"\n... (truncado)"

        log_operation("run_python_script", {"script": script[:50]}, f"exit={result.returncode}")

        if result.returncode != 0:
            return f"⚠️ Script terminó con código {result.returncode}:\n{output}"
        return output if output else "(sin salida)"

    except subprocess.TimeoutExpired:
        return f"⏰ Script excedió timeout de {timeout}s"
    except Exception as e:
        return f"Error ejecutando script: {e}"


def tool_media_control(action: str) -> str:
    try:
        if action == "get_status":
            result = subprocess.run(
                ["playerctl", "status"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return "No hay reproducción activa"
            status = result.stdout.strip()

            result = subprocess.run(
                ["playerctl", "metadata", "title"],
                capture_output=True, text=True, timeout=5
            )
            title = result.stdout.strip() if result.returncode == 0 else "Desconocido"

            result = subprocess.run(
                ["playerctl", "metadata", "artist"],
                capture_output=True, text=True, timeout=5
            )
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


def tool_send_notification(title: str, message: str, urgency: str = "normal", icon: str = None, timeout: int = 5000, category: str = None, transient: bool = False) -> str:
    """Send desktop notification with advanced options."""
    try:
        cmd = ["notify-send"]
        
        # Urgency
        if urgency in ["low", "normal", "critical"]:
            cmd.extend(["-u", urgency])
        
        # Timeout
        if timeout > 0:
            cmd.extend(["-t", str(timeout)])
        
        # Icon
        if icon:
            if icon.startswith("/") or icon.startswith("~"):
                cmd.extend(["-i", os.path.expanduser(icon)])
            else:
                # Stock icon name
                cmd.extend(["-i", icon])
        
        # Category
        if category:
            cmd.extend(["-c", category])
        
        # Transient
        if transient:
            cmd.append("-e")
        
        # App name
        cmd.extend(["-a", "AI Lab"])
        
        # Title and message
        cmd.append(title)
        if message:
            cmd.append(message)
        
        subprocess.run(cmd, capture_output=True, timeout=5)
        
        log_operation("send_notification", {"title": title, "urgency": urgency}, "sent")
        
        result = f"🔔 Notificación enviada: {title}"
        if urgency == "critical":
            result += " (CRÍTICA)"
        elif urgency == "low":
            result += " (baja prioridad)"
        
        return result
    
    except FileNotFoundError:
        return "Error: notify-send no encontrado"
    except Exception as e:
        return f"Error enviando notificación: {e}"


SPOTIFY_PLAYER = os.path.join(HOME, ".cargo/bin/spotify_player")


def tool_spotify_search(query: str, limit: int = 5) -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "search", query],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return f"Error en búsqueda: {result.stderr}"

        data = json.loads(result.stdout)
        lines = [f"🔍 Resultados para '{query}':\n"]

        tracks = data.get("tracks", [])[:limit]
        for i, track in enumerate(tracks, 1):
            name = track.get("name", "Desconocido")
            artists = ", ".join(a.get("name", "") for a in track.get("artists", []))
            album = track.get("album", {}).get("name", "")
            lines.append(f"  {i}. {name} - {artists} ({album})")

        playlists = data.get("playlists", [])[:3]
        if playlists:
            lines.append(f"\n📋 Playlists:")
            for pl in playlists:
                lines.append(f"  - {pl.get('name', '')}")

        artists = data.get("artists", [])[:3]
        if artists:
            lines.append(f"\n👤 Artistas:")
            for a in artists:
                lines.append(f"  - {a.get('name', '')}")

        log_operation("spotify_search", {"query": query}, f"{len(tracks)} tracks")
        return "\n".join(lines)
    except json.JSONDecodeError:
        return "Error parseando resultados de Spotify"
    except FileNotFoundError:
        return f"Error: spotify_player no encontrado en {SPOTIFY_PLAYER}"
    except Exception as e:
        return f"Error en búsqueda Spotify: {e}"


def tool_spotify_now() -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "get", "key", "current_playback"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return "No hay canción reproduciéndose actualmente"

        data = json.loads(result.stdout)
        if not data:
            return "No hay canción reproduciéndose actualmente"

        track = data.get("item", {})
        name = track.get("name", "Desconocido")
        artists = ", ".join(a.get("name", "") for a in track.get("artists", []))
        album = track.get("album", {}).get("name", "")
        is_playing = data.get("is_playing", False)
        progress = data.get("progress_ms", 0) // 1000
        duration = track.get("duration_ms", 0) // 1000

        status = "▶️ Reproduciendo" if is_playing else "⏸️ Pausado"
        mins_prog = progress // 60
        secs_prog = progress % 60
        mins_dur = duration // 60
        secs_dur = duration % 60

        log_operation("spotify_now", {}, name)
        return f"{status}: {name} - {artists}\nÁlbum: {album}\n{mins_prog}:{secs_prog:02d} / {mins_dur}:{secs_dur:02d}"
    except json.JSONDecodeError:
        return "Error parseando datos de Spotify"
    except Exception as e:
        return f"Error obteniendo estado: {e}"


def tool_spotify_play() -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "playback", "play"],
            capture_output=True, text=True, timeout=10
        )
        log_operation("spotify_play", {}, "play")
        return "▶️ Reproduciendo en Spotify"
    except Exception as e:
        return f"Error: {e}"


def tool_spotify_pause() -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "playback", "pause"],
            capture_output=True, text=True, timeout=10
        )
        log_operation("spotify_pause", {}, "pause")
        return "⏸️ Spotify pausado"
    except Exception as e:
        return f"Error: {e}"


def tool_spotify_next() -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "playback", "next"],
            capture_output=True, text=True, timeout=10
        )
        log_operation("spotify_next", {}, "next")
        return "⏭️ Siguiente canción"
    except Exception as e:
        return f"Error: {e}"


def tool_spotify_previous() -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "playback", "previous"],
            capture_output=True, text=True, timeout=10
        )
        log_operation("spotify_previous", {}, "previous")
        return "⏮️ Canción anterior"
    except Exception as e:
        return f"Error: {e}"


def tool_spotify_volume(level: int) -> str:
    level = max(0, min(100, level))
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "playback", "volume", str(level)],
            capture_output=True, text=True, timeout=10
        )
        log_operation("spotify_volume", {"level": level}, "set")
        return f"🔊 Volumen Spotify: {level}%"
    except Exception as e:
        return f"Error: {e}"


def tool_spotify_playlists() -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "get", "key", "playlists"],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return "Error obteniendo playlists"

        data = json.loads(result.stdout)
        if not data:
            return "No se encontraron playlists"

        lines = ["📋 Tus playlists:\n"]
        items = data.get("items", [])[:20]
        for i, pl in enumerate(items, 1):
            name = pl.get("name", "Sin nombre")
            tracks = pl.get("tracks", {}).get("total", 0)
            lines.append(f"  {i}. {name} ({tracks} canciones)")

        log_operation("spotify_playlists", {}, f"{len(items)} playlists")
        return "\n".join(lines)
    except json.JSONDecodeError:
        return "Error parseando playlists"
    except Exception as e:
        return f"Error obteniendo playlists: {e}"


def tool_spotify_launch() -> str:
    try:
        result = subprocess.run(
            ["pgrep", "-x", "spotify"],
            capture_output=True, text=True, timeout=5
        )
        if result.stdout.strip():
            return "Spotify ya está corriendo"

        subprocess.Popen(
            ["spotify"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True
        )
        log_operation("spotify_launch", {}, "launched")
        return "🎵 Spotify abierto"
    except Exception as e:
        return f"Error abriendo Spotify: {e}"


def tool_spotify_play_track(query: str) -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "search", query],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return f"Error buscando: {result.stderr}"

        data = json.loads(result.stdout)
        tracks = data.get("tracks", [])
        if not tracks:
            return f"No encontré canciones para '{query}'"

        track = tracks[0]
        track_name = track.get("name", "")
        track_id = track.get("id", "")
        artists = ", ".join(a.get("name", "") for a in track.get("artists", []))

        result = subprocess.run(
            [SPOTIFY_PLAYER, "playback", "start", "track", "--id", track_id],
            capture_output=True, text=True, timeout=10
        )

        log_operation("spotify_play_track", {"query": query}, track_name)
        return f"▶️ Reproduciendo: {track_name} - {artists}"
    except json.JSONDecodeError:
        return "Error parseando resultados"
    except Exception as e:
        return f"Error reproduciendo canción: {e}"


def tool_spotify_play_artist(artist: str) -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "playback", "start", "context", "--name", artist],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return f"Error reproduciendo artista: {result.stderr}"

        log_operation("spotify_play_artist", {"artist": artist}, "playing")
        return f"▶️ Reproduciendo música de: {artist}"
    except Exception as e:
        return f"Error: {e}"


def tool_spotify_play_playlist(name: str) -> str:
    try:
        result = subprocess.run(
            [SPOTIFY_PLAYER, "playback", "start", "context", "--name", name],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return f"Error reproduciendo playlist: {result.stderr}"

        log_operation("spotify_play_playlist", {"name": name}, "playing")
        return f"▶️ Reproduciendo playlist: {name}"
    except Exception as e:
        return f"Error: {e}"


# ── New Tools Implementations ────────────────────────────────
NOTES_DIR = os.path.join(HOME, ".notes")
MEMORY_DB = os.path.join(HOME, ".config/ai-memory.db")


def tool_screenshot(filename: str = None, delay: int = 0) -> str:
    try:
        screenshots_dir = os.path.join(HOME, "Pictures/screenshots")
        os.makedirs(screenshots_dir, exist_ok=True)

        if not filename:
            filename = datetime.now().strftime("%Y%m%d_%H%M%S")

        filepath = os.path.join(screenshots_dir, f"{filename}.png")

        cmd = ["gnome-screenshot", "-f", filepath]
        if delay > 0:
            cmd = ["gnome-screenshot", "-d", str(delay), "-f", filepath]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)

        if os.path.exists(filepath):
            size = format_size(os.path.getsize(filepath))
            log_operation("screenshot", {"filename": filename}, f"saved {size}")
            return f"Screenshot guardada: {filepath} ({size})"

        return f"Error: No se pudo crear la screenshot"

    except FileNotFoundError:
        return "Error: gnome-screenshot no encontrado"
    except Exception as e:
        return f"Error creando screenshot: {e}"


def tool_clipboard(action: str, text: str = None) -> str:
    try:
        if action == "copy":
            if not text:
                return "Error: Se requiere texto para copiar"
            proc = subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=text.encode(),
                capture_output=True,
                timeout=5
            )
            log_operation("clipboard", {"action": "copy"}, text[:50])
            return f"📋 Copiado al clipboard: {text[:100]}"

        elif action == "paste":
            result = subprocess.run(
                ["xclip", "-selection", "clipboard", "-o"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                return f"📋 Clipboard: {result.stdout}"
            return "Clipboard vacío"

        elif action == "clear":
            subprocess.run(
                ["xclip", "-selection", "clipboard"],
                input=b"",
                capture_output=True,
                timeout=5
            )
            return "📋 Clipboard limpiado"

        else:
            return f"Acción no reconocida: {action}"

    except FileNotFoundError:
        return "Error: xclip no encontrado"
    except Exception as e:
        return f"Error con clipboard: {e}"


def tool_brightness(action: str, level: int = None) -> str:
    try:
        backlight_path = "/sys/class/backlight"
        if not os.path.exists(backlight_path):
            return "Error: No se encontró control de brillo"

        devices = os.listdir(backlight_path)
        if not devices:
            return "Error: No hay dispositivos de brillo"

        device = devices[0]
        max_brightness_file = os.path.join(backlight_path, device, "max_brightness")
        brightness_file = os.path.join(backlight_path, device, "brightness")

        with open(max_brightness_file) as f:
            max_brightness = int(f.read().strip())

        if action == "get":
            with open(brightness_file) as f:
                current = int(f.read().strip())
            percentage = int((current / max_brightness) * 100)
            return f"☀️ Brillo actual: {percentage}% ({current}/{max_brightness})"

        elif action == "set":
            if level is None:
                return "Error: Se requiere nivel para action=set"
            level = max(0, min(100, level))
            new_brightness = int((level / 100) * max_brightness)
            subprocess.run(["tee", brightness_file], input=str(new_brightness).encode(), timeout=5)
            return f"☀️ Brillo establecido a {level}%"

        elif action == "up":
            with open(brightness_file) as f:
                current = int(f.read().strip())
            increment = max(1, max_brightness // 20)
            new_brightness = min(max_brightness, current + increment)
            subprocess.run(["tee", brightness_file], input=str(new_brightness).encode(), timeout=5)
            percentage = int((new_brightness / max_brightness) * 100)
            return f"☀️ Brillo subido a {percentage}%"

        elif action == "down":
            with open(brightness_file) as f:
                current = int(f.read().strip())
            decrement = max(1, max_brightness // 20)
            new_brightness = max(0, current - decrement)
            subprocess.run(["tee", brightness_file], input=str(new_brightness).encode(), timeout=5)
            percentage = int((new_brightness / max_brightness) * 100)
            return f"☀️ Brillo bajado a {percentage}%"

        else:
            return f"Acción no reconocida: {action}"

    except PermissionError:
        return "Error: Sin permisos para cambiar brillo (necesita sudo o grupo video)"
    except Exception as e:
        return f"Error controlando brillo: {e}"


def tool_weather(city: str = None) -> str:
    try:
        if city:
            url = f"https://wttr.in/{city}?format=%l:+%C+%t+%h+%w"
        else:
            url = "https://wttr.in/?format=%l:+%C+%t+%h+%w"

        result = subprocess.run(
            ["curl", "-s", "--max-time", "10", url],
            capture_output=True,
            text=True,
            timeout=15
        )

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


def tool_timer(minutes: int, message: str) -> str:
    try:
        seconds = minutes * 60

        timer_script = f"""
import time
import subprocess
time.sleep({seconds})
subprocess.run(['notify-send', '⏱️ Temporizador', '{message}'])
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


def tool_notes(action: str, title: str = None, content: str = None, category: str = "General") -> str:
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


# ── Memory Tools ──────────────────────────────────────────
def _get_db():
    import sqlite3
    conn = sqlite3.connect(MEMORY_DB)
    conn.row_factory = sqlite3.Row
    return conn


def tool_memory_save(category: str, content: str, title: str = None, tags: str = "") -> str:
    try:
        conn = _get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO memories (category, title, content, tags) VALUES (?, ?, ?, ?)",
            (category, title, content, tags)
        )
        conn.commit()
        entry_id = cursor.lastrowid
        conn.close()

        log_operation("memory_save", {"category": category, "title": title}, f"id={entry_id}")
        return f"💾 Guardado en memoria: [{category}] {title or content[:50]} (ID: {entry_id})"

    except Exception as e:
        return f"Error guardando en memoria: {e}"


def tool_memory_search(query: str, category: str = None, limit: int = 10) -> str:
    try:
        conn = _get_db()
        cursor = conn.cursor()

        if category:
            cursor.execute(
                "SELECT * FROM memories WHERE category = ? AND (content LIKE ? OR title LIKE ? OR tags LIKE ?) ORDER BY created_at DESC LIMIT ?",
                (category, f"%{query}%", f"%{query}%", f"%{query}%", limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM memories WHERE content LIKE ? OR title LIKE ? OR tags LIKE ? ORDER BY created_at DESC LIMIT ?",
                (f"%{query}%", f"%{query}%", f"%{query}%", limit)
            )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return f"No se encontraron resultados para: {query}"

        lines = [f"🔍 Resultados para '{query}' ({len(rows)} entradas):\n"]
        for row in rows:
            tags_str = f" [{row['tags']}]" if row['tags'] else ""
            lines.append(f"  [{row['id']}] {row['category']}: {row['title'] or row['content'][:60]}{tags_str}")
            lines.append(f"      {row['created_at']}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error buscando en memoria: {e}"


def tool_memory_context(category: str = None, limit: int = 5) -> str:
    try:
        conn = _get_db()
        cursor = conn.cursor()

        if category:
            cursor.execute(
                "SELECT * FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT ?",
                (category, limit)
            )
        else:
            cursor.execute(
                "SELECT * FROM memories ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )

        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No hay entradas en memoria"

        lines = ["📚 Contexto de memoria reciente:\n"]
        for row in rows:
            lines.append(f"[{row['category']}] {row['title'] or 'Sin título'}")
            lines.append(f"  {row['content'][:200]}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"Error obteniendo contexto: {e}"


def tool_memory_list(limit: int = 20) -> str:
    try:
        conn = _get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No hay entradas en memoria"

        lines = [f"📋 Memoria ({len(rows)} entradas):\n"]
        for row in rows:
            lines.append(f"  [{row['id']}] {row['category']}: {row['title'] or row['content'][:50]}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error listando memoria: {e}"


def tool_memory_delete(id: int) -> str:
    try:
        conn = _get_db()
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM memories WHERE id = ?", (id,))
        row = cursor.fetchone()

        if not row:
            conn.close()
            return f"Error: No se encontró entrada con ID {id}"

        cursor.execute("DELETE FROM memories WHERE id = ?", (id,))
        conn.commit()
        conn.close()

        log_operation("memory_delete", {"id": id}, "deleted")
        return f"🗑️ Eliminada entrada [{id}]: {row['title'] or row['content'][:50]}"

    except Exception as e:
        return f"Error eliminando de memoria: {e}"


# ── System Tools ────────────────────────────────────────────
def tool_system_shutdown(action: str, delay: int = 0, confirm: bool = False) -> str:
    if not confirm:
        return f"⚠️ Acción destructiva: {action}. Responde con confirm=true para ejecutar."

    try:
        if action == "shutdown":
            cmd = f"shutdown -h +{delay // 60 if delay >= 60 else 0}" if delay > 0 else "shutdown -h now"
        elif action == "reboot":
            cmd = f"shutdown -r +{delay // 60 if delay >= 60 else 0}" if delay > 0 else "shutdown -r now"
        elif action == "suspend":
            cmd = "systemctl suspend"
        elif action == "hibernate":
            cmd = "systemctl hibernate"
        else:
            return f"Acción no reconocida: {action}"

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        log_operation("system_shutdown", {"action": action}, "executed")
        return f"✅ {action} ejecutado"

    except Exception as e:
        return f"Error en {action}: {e}"


# ── File Tools ─────────────────────────────────────────────
def tool_file_compress(source: str, format: str = "tar.gz") -> str:
    source = safe_path(source)
    if not os.path.exists(source):
        return f"Error: No existe: {source}"

    try:
        base_name = os.path.basename(source)
        if format == "tar.gz":
            dest = f"{source}.tar.gz"
            result = subprocess.run(
                ["tar", "-czf", dest, "-C", os.path.dirname(source), base_name],
                capture_output=True, text=True, timeout=60
            )
        elif format == "zip":
            dest = f"{source}.zip"
            result = subprocess.run(
                ["zip", "-r", dest, source],
                capture_output=True, text=True, timeout=60
            )
        else:
            return f"Formato no soportado: {format}"

        if result.returncode != 0:
            return f"Error comprimiendo: {result.stderr}"

        size = format_size(os.path.getsize(dest))
        log_operation("file_compress", {"source": source, "format": format}, f"{dest} ({size})")
        return f"✅ Comprimido: {dest} ({size})"

    except Exception as e:
        return f"Error comprimiendo: {e}"


def tool_file_extract(source: str, destination: str = None) -> str:
    source = safe_path(source)
    if not os.path.exists(source):
        return f"Error: No existe: {source}"

    try:
        if destination:
            dest = safe_path(destination)
            os.makedirs(dest, exist_ok=True)
        else:
            dest = os.path.dirname(source)

        if source.endswith(".tar.gz") or source.endswith(".tgz"):
            result = subprocess.run(
                ["tar", "-xzf", source, "-C", dest],
                capture_output=True, text=True, timeout=60
            )
        elif source.endswith(".zip"):
            result = subprocess.run(
                ["unzip", "-o", source, "-d", dest],
                capture_output=True, text=True, timeout=60
            )
        elif source.endswith(".tar.bz2"):
            result = subprocess.run(
                ["tar", "-xjf", source, "-C", dest],
                capture_output=True, text=True, timeout=60
            )
        else:
            return f"Formato no soportado: {source}"

        if result.returncode != 0:
            return f"Error extrayendo: {result.stderr}"

        log_operation("file_extract", {"source": source}, f"to {dest}")
        return f"✅ Extraído en: {dest}"

    except Exception as e:
        return f"Error extrayendo: {e}"


def tool_file_permissions(path: str, mode: str) -> str:
    path = safe_path(path)
    if not os.path.exists(path):
        return f"Error: No existe: {path}"

    try:
        if mode.startswith("+") or mode.startswith("-"):
            cmd = f"chmod {mode} {path}"
        else:
            cmd = f"chmod {mode} {path}"

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return f"Error cambiando permisos: {result.stderr}"

        log_operation("file_permissions", {"path": path, "mode": mode}, "changed")
        return f"✅ Permisos cambiados: {path} → {mode}"

    except Exception as e:
        return f"Error cambiando permisos: {e}"


# ── Network Tools ──────────────────────────────────────────
def tool_network_ping(host: str, count: int = 4) -> str:
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), host],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            return f"❌ No se pudo hacer ping a {host}"

        lines = result.stdout.strip().split("\n")
        stats_line = [l for l in lines if "avg" in l]
        if stats_line:
            return f"✅ Ping {host}: {stats_line[0]}"
        return f"✅ Ping {host}: OK"

    except subprocess.TimeoutExpired:
        return f"⏰ Timeout haciendo ping a {host}"
    except Exception as e:
        return f"Error haciendo ping: {e}"


def tool_network_ports(filter: str = "LISTEN") -> str:
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return "Error obteniendo puertos"

        lines = result.stdout.strip().split("\n")
        filtered = [l for l in lines if filter.upper() in l.upper()]

        if not filtered:
            return f"No hay puertos con estado: {filter}"

        return f"🔌 Puertos ({filter}):\n" + "\n".join(filtered[:20])

    except Exception as e:
        return f"Error obteniendo puertos: {e}"


def tool_network_speed() -> str:
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{speed_download}", "https://speed.cloudflare.com/__down?bytes=1000000"],
            capture_output=True, text=True, timeout=30
        )

        speed_bps = float(result.stdout) if result.stdout else 0
        speed_mbps = speed_bps / 1024 / 1024

        return f"🌐 Velocidad de descarga: {speed_mbps:.2f} MB/s"

    except Exception as e:
        return f"Error midiendo velocidad: {e}"


def tool_network_info() -> str:
    try:
        info = []

        # Get IP addresses
        result = subprocess.run(["ip", "-4", "addr", "show"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "inet " in line and "127.0.0.1" not in line:
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p == "inet":
                            info.append(f"IP: {parts[i+1]}")
                            break

        # Get gateway
        result = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.split()
            for i, p in enumerate(parts):
                if p == "via":
                    info.append(f"Gateway: {parts[i+1]}")
                    break

        # Get DNS
        try:
            with open("/etc/resolv.conf") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        info.append(f"DNS: {line.split()[1]}")
        except:
            pass

        return "🌐 Red:\n" + "\n".join(f"  {i}" for i in info) if info else "No se pudo obtener info de red"

    except Exception as e:
        return f"Error obteniendo info de red: {e}"


# ── Process Tools ──────────────────────────────────────────
def tool_process_list(sort_by: str = "cpu", limit: int = 20) -> str:
    try:
        if sort_by == "cpu":
            cmd = "ps aux --sort=-%cpu"
        elif sort_by == "memory":
            cmd = "ps aux --sort=-%mem"
        else:
            cmd = "ps aux"

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return "Error obteniendo procesos"

        lines = result.stdout.strip().split("\n")
        header = lines[0]
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


def tool_process_kill(pid: int = None, name: str = None, signal: str = "TERM", confirm: bool = False) -> str:
    if not confirm:
        target = f"PID {pid}" if pid else f"proceso {name}"
        return f"⚠️ Acción destructiva: terminar {target} con señal {signal}. Responde con confirm=true."

    try:
        if pid:
            cmd = f"kill -{signal} {pid}"
        elif name:
            cmd = f"pkill -{signal} {name}"
        else:
            return "Error: Se requiere PID o nombre"

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)

        if result.returncode != 0:
            return f"Error terminando proceso: {result.stderr}"

        target = f"PID {pid}" if pid else f"proceso {name}"
        log_operation("process_kill", {"pid": pid, "name": name, "signal": signal}, "killed")
        return f"✅ {target} terminado con señal {signal}"

    except Exception as e:
        return f"Error terminando proceso: {e}"


def tool_process_search(query: str) -> str:
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


# ── Cron Tools ─────────────────────────────────────────────
def tool_cron_list() -> str:
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


def tool_cron_add(schedule: str, command: str, description: str = None) -> str:
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


def tool_cron_delete(line_number: int) -> str:
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


# ── Audio Tools ────────────────────────────────────────────
def tool_audio_list_devices() -> str:
    try:
        result = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            capture_output=True, text=True, timeout=5
        )

        output = ["🔊 Dispositivos de salida:\n"]
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split()
                    output.append(f"  • {parts[1]} (State: {parts[2]})")

        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True, text=True, timeout=5
        )

        output.append("\n🎤 Dispositivos de entrada:\n")
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split()
                    output.append(f"  • {parts[1]} (State: {parts[2]})")

        return "\n".join(output)

    except Exception as e:
        return f"Error listando dispositivos de audio: {e}"


def tool_audio_set_source(sink: str) -> str:
    try:
        result = subprocess.run(
            ["pactl", "set-default-sink", sink],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            return f"Error cambiando sink: {result.stderr}"

        log_operation("audio_set_source", {"sink": sink}, "changed")
        return f"✅ Sink cambiado a: {sink}"

    except Exception as e:
        return f"Error cambiando sink: {e}"


def tool_audio_set_source_input(source: str) -> str:
    try:
        result = subprocess.run(
            ["pactl", "set-default-source", source],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            return f"Error cambiando source: {result.stderr}"

        log_operation("audio_set_source_input", {"source": source}, "changed")
        return f"✅ Source cambiado a: {source}"

    except Exception as e:
        return f"Error cambiando source: {e}"


# ── Monitoring Tools ───────────────────────────────────────
def tool_monitor_realtime(metrics: str = "all") -> str:
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


def tool_monitor_top_processes(by: str = "cpu", limit: int = 10) -> str:
    try:
        if by == "cpu":
            cmd = "ps aux --sort=-%cpu"
        else:
            cmd = "ps aux --sort=-%mem"

        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)

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


def tool_disk_usage() -> str:
    try:
        result = subprocess.run(
            ["df", "-h", "--output=source,size,used,avail,pcent,target"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return "Error obteniendo uso de disco"

        lines = result.stdout.strip().split("\n")
        output = ["💾 Uso de disco:\n"]
        output.append(lines[0])  # Header

        for line in lines[1:]:
            if line.startswith("/dev/"):
                output.append(line)

        return "\n".join(output)

    except Exception as e:
        return f"Error obteniendo uso de disco: {e}"


def tool_disk_io() -> str:
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


# ── GitHub Tools ────────────────────────────────────────────
GH = "gh"


def _gh(args: list, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            [GH] + args,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except FileNotFoundError:
        return "Error: GitHub CLI (gh) no instalado"
    except subprocess.TimeoutExpired:
        return "Timeout en operación de GitHub"
    except Exception as e:
        return f"Error: {e}"


def tool_gh_repos_list(limit: int = 20, visibility: str = "all") -> str:
    args = ["repo", "list", "--limit", str(limit), "--json", "name,description,isPrivate,updatedAt,stargazerCount"]
    if visibility and visibility != "all":
        args.extend(["--visibility", visibility])
    output = _gh(args)
    if output.startswith("Error"):
        return output

    try:
        repos = json.loads(output)
        if not repos:
            return "No hay repositorios"

        lines = [f"📦 Repositorios ({len(repos)}):\n"]
        for r in repos:
            vis = "🔒" if r.get("isPrivate") else "🌐"
            stars = f"⭐{r.get('stargazerCount', 0)}" if r.get('stargazerCount', 0) > 0 else ""
            lines.append(f"  {vis} {r['name']} {stars}")
            if r.get('description'):
                lines.append(f"     {r['description'][:80]}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def tool_gh_repo_info(repo: str) -> str:
    output = _gh(["repo", "view", repo, "--json", "name,description,isPrivate,homepageUrl,primaryLanguage,stargazerCount,forkCount,watchers,createdAt,updatedAt,pushedAt,defaultBranchRef"])
    if output.startswith("Error"):
        return output

    try:
        r = json.loads(output)
        lang = r.get('primaryLanguage', {}).get('name', 'N/A') if r.get('primaryLanguage') else 'N/A'
        vis = "Privado" if r.get('isPrivate') else "Público"

        info = [
            f"📦 {r['name']}",
            f"  Descripción: {r.get('description', 'N/A')}",
            f"  Visibilidad: {vis}",
            f"  Lenguaje: {lang}",
            f"  ⭐ Stars: {r.get('stargazerCount', 0)}",
            f"  🍴 Forks: {r.get('forkCount', 0)}",
            f"  👀 Watchers: {r.get('watchers', {}).get('totalCount', 0)}",
            f"  Creado: {r.get('createdAt', 'N/A')}",
            f"  Último push: {r.get('pushedAt', 'N/A')}",
        ]
        return "\n".join(info)
    except json.JSONDecodeError:
        return output


def tool_gh_repo_create(name: str, description: str = None, private: bool = False, auto_init: bool = True) -> str:
    args = ["repo", "create", name]
    if description:
        args.extend(["-d", description])
    if private:
        args.append("--private")
    else:
        args.append("--public")
    if auto_init:
        args.append("--clone")

    output = _gh(args)
    return f"✅ Repositorio creado: {output}" if not output.startswith("Error") else output


def tool_gh_issues_list(repo: str, state: str = "open", limit: int = 20) -> str:
    output = _gh(["issue", "list", "-R", repo, "--state", state, "--limit", str(limit), "--json", "number,title,state,labels,createdAt"])
    if output.startswith("Error"):
        return output

    try:
        issues = json.loads(output)
        if not issues:
            return f"No hay issues {state} en {repo}"

        lines = [f"📋 Issues {state} en {repo} ({len(issues)}):\n"]
        for i in issues:
            labels = ", ".join(l['name'] for l in i.get('labels', []))
            label_str = f" [{labels}]" if labels else ""
            lines.append(f"  #{i['number']} {i['title']}{label_str}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def tool_gh_issue_create(repo: str, title: str, body: str = None, labels: str = None) -> str:
    args = ["issue", "create", "-R", repo, "-t", title]
    if body:
        args.extend(["-b", body])
    if labels:
        args.extend(["-l", labels])

    output = _gh(args)
    return f"✅ Issue creado: {output}" if not output.startswith("Error") else output


def tool_gh_pr_list(repo: str, state: str = "open", limit: int = 20) -> str:
    output = _gh(["pr", "list", "-R", repo, "--state", state, "--limit", str(limit), "--json", "number,title,state,author,createdAt,headRefName,baseRefName"])
    if output.startswith("Error"):
        return output

    try:
        prs = json.loads(output)
        if not prs:
            return f"No hay PRs {state} en {repo}"

        lines = [f"🔀 Pull Requests {state} en {repo} ({len(prs)}):\n"]
        for pr in prs:
            author = pr.get('author', {}).get('login', 'unknown')
            lines.append(f"  #{pr['number']} {pr['title']} (by @{author})")
            lines.append(f"     {pr.get('headRefName', '?')} → {pr.get('baseRefName', '?')}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def tool_gh_pr_create(repo: str, title: str, body: str = None, head: str = None, base: str = "main") -> str:
    args = ["pr", "create", "-R", repo, "-t", title]
    if body:
        args.extend(["-b", body])
    if head:
        args.extend(["-H", head])
    args.extend(["-B", base])

    output = _gh(args)
    return f"✅ PR creado: {output}" if not output.startswith("Error") else output


def tool_gh_pr_merge(repo: str, pr_number: int) -> str:
    output = _gh(["pr", "merge", str(pr_number), "-R", repo, "--merge"])
    return f"✅ PR #{pr_number} mergeado" if not output.startswith("Error") else output


def tool_gh_actions_list(repo: str) -> str:
    output = _gh(["workflow", "list", "-R", repo, "--json", "name,state,createdAt"])
    if output.startswith("Error"):
        return output

    try:
        workflows = json.loads(output)
        if not workflows:
            return f"No hay workflows en {repo}"

        lines = [f"⚙️ Workflows en {repo} ({len(workflows)}):\n"]
        for w in workflows:
            state_icon = {"active": "✅", "disabled": "❌"}.get(w.get('state', ''), "❓")
            lines.append(f"  {state_icon} {w['name']} ({w.get('state', 'unknown')})")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def tool_gh_actions_runs(repo: str, limit: int = 10) -> str:
    output = _gh(["run", "list", "-R", repo, "--limit", str(limit), "--json", "name,status,conclusion,createdAt,event"])
    if output.startswith("Error"):
        return output

    try:
        runs = json.loads(output)
        if not runs:
            return f"No hay runs en {repo}"

        lines = [f"🔄 Runs recientes en {repo} ({len(runs)}):\n"]
        for r in runs:
            status_icon = {"success": "✅", "failure": "❌", "in_progress": "🔄"}.get(r.get('conclusion', r.get('status', '')), "❓")
            lines.append(f"  {status_icon} {r['name']} - {r.get('conclusion', r.get('status', 'unknown'))}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def tool_gh_release_list(repo: str, limit: int = 10) -> str:
    output = _gh(["release", "list", "-R", repo, "--limit", str(limit)])
    if output.startswith("Error"):
        return output

    if not output:
        return f"No hay releases en {repo}"

    return f"📦 Releases en {repo}:\n{output}"


def tool_gh_gist_list(limit: int = 20) -> str:
    output = _gh(["gist", "list", "--limit", str(limit), "--json", "name,description,public,updatedAt"])
    if output.startswith("Error"):
        return output

    try:
        gists = json.loads(output)
        if not gists:
            return "No hay gists"

        lines = [f"📝 Tus Gists ({len(gists)}):\n"]
        for g in gists:
            vis = "🌐" if g.get('public') else "🔒"
            desc = f" - {g['description']}" if g.get('description') else ""
            lines.append(f"  {vis} {g['name']}{desc}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def tool_gh_gist_create(filename: str, content: str, description: str = None, public: bool = False) -> str:
    args = ["gist", "create"]
    if description:
        args.extend(["-d", description])
    if public:
        args.append("--public")
    else:
        args.append("--secret")

    # Create temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix=f"_{filename}", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        args.append(tmp_path)
        output = _gh(args)
        return f"✅ Gist creado: {output}" if not output.startswith("Error") else output
    finally:
        os.unlink(tmp_path)


def tool_gh_search_repos(query: str, limit: int = 10, language: str = None, sort: str = "stars") -> str:
    search_query = query
    if language:
        search_query += f" language:{language}"

    output = _gh(["search", "repos", search_query, "--limit", str(limit), "--sort", sort, "--json", "name,description,stargazersCount,language"])
    if output.startswith("Error"):
        return output

    try:
        repos = json.loads(output)
        if not repos:
            return f"No se encontraron repositorios para: {query}"

        lines = [f"🔍 Repositorios para '{query}' ({len(repos)}):\n"]
        for r in repos:
            stars = f"⭐{r.get('stargazersCount', 0)}" if r.get('stargazersCount', 0) > 0 else ""
            lang = f"({r.get('language', 'N/A')})" if r.get('language') else ""
            lines.append(f"  {r['name']} {stars} {lang}")
            if r.get('description'):
                lines.append(f"     {r['description'][:80]}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def tool_gh_search_code(query: str, repo: str = None, language: str = None, limit: int = 10) -> str:
    search_query = query
    if repo:
        search_query += f" repo:{repo}"
    if language:
        search_query += f" language:{language}"

    output = _gh(["search", "code", search_query, "--limit", str(limit), "--json", "name,path,repository"])
    if output.startswith("Error"):
        return output

    try:
        results = json.loads(output)
        if not results:
            return f"No se encontró código para: {query}"

        lines = [f"🔍 Código para '{query}' ({len(results)} resultados):\n"]
        for r in results:
            repo_name = r.get('repository', {}).get('name', 'unknown')
            lines.append(f"  {repo_name}/{r['path']}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


# ── Git Tools ──────────────────────────────────────────────
def _git(args: list, path: str = None, timeout: int = 30) -> str:
    try:
        cmd = ["git"] + args
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout,
            cwd=path or os.getcwd()
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except FileNotFoundError:
        return "Error: Git no instalado"
    except Exception as e:
        return f"Error: {e}"


def tool_git_status(path: str = None) -> str:
    output = _git(["status", "--short"], path)
    if output.startswith("Error"):
        return output

    if not output:
        return "✅ Working tree limpio"

    lines = [f"📊 Estado Git:\n"]
    for line in output.split("\n"):
        if line.strip():
            lines.append(f"  {line}")

    return "\n".join(lines)


def tool_git_log(path: str = None, limit: int = 10, branch: str = None) -> str:
    args = ["log", f"--oneline", f"-{limit}"]
    if branch:
        args.append(branch)

    output = _git(args, path)
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay commits"

    return f"📜 Historial ({limit} commits):\n{output}"


def tool_git_diff(path: str = None, file: str = None, staged: bool = False) -> str:
    args = ["diff"]
    if staged:
        args.append("--staged")
    if file:
        args.append(file)

    output = _git(args, path)
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay cambios"

    lines = output.split("\n")[:50]
    return f"📝 Diferencias:\n" + "\n".join(lines) + ("\n... (truncado)" if len(output.split("\n")) > 50 else "")


def tool_git_branches(path: str = None) -> str:
    output = _git(["branch", "-a"], path)
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay branches"

    lines = ["🌿 Branches:\n"]
    for line in output.split("\n"):
        if line.strip():
            lines.append(f"  {line}")

    return "\n".join(lines)


def tool_git_commit(path: str = None, message: str = None, add_all: bool = False) -> str:
    if not message:
        return "Error: Se requiere mensaje de commit"

    if add_all:
        _git(["add", "-A"], path)

    output = _git(["commit", "-m", message], path)
    if output.startswith("Error"):
        return output

    log_operation("git_commit", {"message": message}, "committed")
    return f"✅ Commit creado: {message}"


def tool_git_push(path: str = None, branch: str = None) -> str:
    args = ["push"]
    if branch:
        args.extend(["origin", branch])
    else:
        args.append("origin")

    output = _git(args, path)
    if output.startswith("Error"):
        return output

    log_operation("git_push", {}, "pushed")
    return f"✅ Push completado\n{output}" if output else "✅ Push completado"


def tool_git_pull(path: str = None) -> str:
    output = _git(["pull", "origin"], path)
    if output.startswith("Error"):
        return output

    log_operation("git_pull", {}, "pulled")
    return f"✅ Pull completado\n{output}" if output else "✅ Pull completado"


def tool_git_clone(url: str, destination: str = None) -> str:
    args = ["clone", url]
    if destination:
        args.append(destination)

    output = _git(args)
    if output.startswith("Error"):
        return output

    log_operation("git_clone", {"url": url}, "cloned")
    return f"✅ Repositorio clonado: {url}"


# ── Code Analysis Tools ───────────────────────────────────
def tool_code_analyze(path: str) -> str:
    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: No existe: {target}"

    try:
        with open(target, "r", errors="replace") as f:
            content = f.read()

        lines = content.split("\n")
        total_lines = len(lines)
        blank_lines = sum(1 for l in lines if not l.strip())
        comment_lines = sum(1 for l in lines if l.strip().startswith(("#", "//", "/*", "*", "<!--")))
        code_lines = total_lines - blank_lines - comment_lines

        ext = os.path.splitext(target)[1]
        size = format_size(os.path.getsize(target))

        info = [
            f"📄 Análisis de {os.path.basename(target)}",
            f"  Tamaño: {size}",
            f"  Extension: {ext}",
            f"  Líneas totales: {total_lines}",
            f"  Código: {code_lines}",
            f"  Comentarios: {comment_lines}",
            f"  En blanco: {blank_lines}",
        ]

        return "\n".join(info)

    except Exception as e:
        return f"Error analizando archivo: {e}"


def tool_code_count_lines(path: str = None, extension: str = None) -> str:
    target = safe_path(path) if path else os.getcwd()

    if not os.path.isdir(target):
        return f"Error: No es directorio: {target}"

    try:
        total = 0
        by_ext = {}

        for root, dirs, files in os.walk(target):
            # Skip hidden dirs and common non-code dirs
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", "__pycache__", "venv", ".venv", "vendor"]]

            for f in files:
                if extension and not f.endswith(f".{extension}"):
                    continue

                filepath = os.path.join(root, f)
                try:
                    with open(filepath, "r", errors="replace") as fh:
                        lines = sum(1 for _ in fh)
                        total += lines

                        ext = os.path.splitext(f)[1] or "no_ext"
                        by_ext[ext] = by_ext.get(ext, 0) + lines
                except:
                    pass

        lines = [f"📊 Líneas de código en {target}:\n"]
        lines.append(f"  Total: {total} líneas\n")
        lines.append("  Por extensión:")

        for ext, count in sorted(by_ext.items(), key=lambda x: -x[1])[:15]:
            lines.append(f"    {ext}: {count}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error contando líneas: {e}"


def tool_code_search_pattern(pattern: str, path: str = None, extension: str = None) -> str:
    target = safe_path(path) if path else os.getcwd()

    try:
        cmd = ["grep", "-rn", "--include", f"*.{extension}" if extension else "*", pattern, target]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return f"No se encontró el patrón: {pattern}"

        matches = result.stdout.strip().split("\n")
        lines = [f"🔍 Patrón '{pattern}' ({len(matches)} coincidencias):\n"]

        for match in matches[:20]:
            lines.append(f"  {match}")

        if len(matches) > 20:
            lines.append(f"\n  ... y {len(matches) - 20} más")

        return "\n".join(lines)

    except Exception as e:
        return f"Error buscando patrón: {e}"


# ── Project Tools ──────────────────────────────────────────
def tool_project_dependencies(path: str = None) -> str:
    target = safe_path(path) if path else os.getcwd()

    deps = []

    # Python
    req_file = os.path.join(target, "requirements.txt")
    if os.path.exists(req_file):
        with open(req_file) as f:
            deps.append(("Python (requirements.txt)", [l.strip() for l in f if l.strip() and not l.startswith("#")]))

    # Node.js
    pkg_file = os.path.join(target, "package.json")
    if os.path.exists(pkg_file):
        try:
            with open(pkg_file) as f:
                pkg = json.load(f)
                all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                deps.append(("Node.js (package.json)", list(all_deps.keys())))
        except:
            pass

    # Rust
    cargo_file = os.path.join(target, "Cargo.toml")
    if os.path.exists(cargo_file):
        with open(cargo_file) as f:
            in_deps = False
            rust_deps = []
            for line in f:
                if "[dependencies]" in line:
                    in_deps = True
                elif line.startswith("["):
                    in_deps = False
                elif in_deps and "=" in line:
                    rust_deps.append(line.split("=")[0].strip())
            deps.append(("Rust (Cargo.toml)", rust_deps))

    if not deps:
        return f"No se encontraron dependencias en {target}"

    lines = [f"📦 Dependencias en {target}:\n"]
    for name, dep_list in deps:
        lines.append(f"  {name}:")
        for d in dep_list[:20]:
            lines.append(f"    • {d}")
        if len(dep_list) > 20:
            lines.append(f"    ... y {len(dep_list) - 20} más")
        lines.append("")

    return "\n".join(lines)


def tool_project_structure(path: str = None, depth: int = 3) -> str:
    target = safe_path(path) if path else os.getcwd()

    if not os.path.isdir(target):
        return f"Error: No es directorio: {target}"

    try:
        lines = [f"📁 Estructura de {os.path.basename(target)}:\n"]

        def tree(dir_path, prefix="", current_depth=0):
            if current_depth >= depth:
                return

            try:
                entries = sorted(os.listdir(dir_path))
            except PermissionError:
                return

            dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e)) and not e.startswith(".") and e not in ["node_modules", "__pycache__", "venv", ".venv"]]
            files = [e for e in entries if os.path.isfile(os.path.join(dir_path, e)) and not e.startswith(".")]

            for d in dirs[:10]:
                lines.append(f"{prefix}├── {d}/")
                tree(os.path.join(dir_path, d), prefix + "│   ", current_depth + 1)

            for f in files[:5]:
                lines.append(f"{prefix}└── {f}")

            if len(dirs) > 10:
                lines.append(f"{prefix}└── ... ({len(dirs) - 10} más)")

        tree(target)
        return "\n".join(lines)

    except Exception as e:
        return f"Error mostrando estructura: {e}"


# ── Docker Tools ───────────────────────────────────────────
def _docker(args: list, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except FileNotFoundError:
        return "Error: Docker no instalado"
    except Exception as e:
        return f"Error: {e}"


def tool_docker_ps(all: bool = False) -> str:
    args = ["ps", "--format", "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"]
    if all:
        args.append("-a")

    output = _docker(args)
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay contenedores"

    return f"🐳 Contenedores:\n{output}"


def tool_docker_logs(container: str, lines_count: int = 50) -> str:
    output = _docker(["logs", "--tail", str(lines_count), container])
    if output.startswith("Error"):
        return output

    return f"📜 Logs de {container} (últimas {lines_count} líneas):\n{output}"


def tool_docker_images() -> str:
    output = _docker(["images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"])
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay imágenes"

    return f"🐳 Imágenes:\n{output}"


# ── Chat Export Tools ──────────────────────────────────────
CHAT_SHARE_DIR = os.path.join(HOME, "ai-lab/shared-chats")
CHAT_SHARE_URL = "http://localhost:9094"


def tool_chat_export(messages: str, title: str = None) -> str:
    try:
        msg_list = json.loads(messages)
        if not isinstance(msg_list, list):
            return "Error: messages debe ser un array de objetos"

        import secrets
        chat_id = secrets.token_urlsafe(8)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        if not title:
            title = f"Chat_{timestamp}"

        chat_data = {
            "id": chat_id,
            "title": title,
            "created_at": datetime.now().isoformat(),
            "messages": msg_list
        }

        os.makedirs(CHAT_SHARE_DIR, exist_ok=True)

        # Save JSON
        json_path = os.path.join(CHAT_SHARE_DIR, f"{chat_id}.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(chat_data, f, ensure_ascii=False, indent=2)

        # Save Markdown
        md_path = os.path.join(CHAT_SHARE_DIR, f"{chat_id}.md")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# {title}\n\n")
            f.write(f"*Exportado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n---\n\n")
            for msg in msg_list:
                role = msg.get("role", "unknown")
                content = msg.get("content", "")
                if role == "user":
                    f.write(f"## 👤 Usuario\n\n{content}\n\n")
                elif role == "assistant":
                    f.write(f"## 🤖 Asistente\n\n{content}\n\n")
                f.write("---\n\n")

        share_url = f"{CHAT_SHARE_URL}/chat/{chat_id}"

        log_operation("chat_export", {"title": title}, f"{len(msg_list)} messages")
        return (
            f"✅ Chat exportado: {title}\n\n"
            f"📎 Enlace: {share_url}\n"
            f"📄 JSON: {json_path}\n"
            f"📝 Markdown: {md_path}\n"
            f"🔢 ID: {chat_id}\n"
            f"💬 Mensajes: {len(msg_list)}"
        )

    except json.JSONDecodeError:
        return "Error: messages no es JSON válido"
    except Exception as e:
        return f"Error exportando chat: {e}"


def tool_chat_list_shared() -> str:
    try:
        if not os.path.exists(CHAT_SHARE_DIR):
            return "No hay chats compartidos"

        chats = []
        for filename in os.listdir(CHAT_SHARE_DIR):
            if filename.endswith(".json"):
                filepath = os.path.join(CHAT_SHARE_DIR, filename)
                try:
                    with open(filepath) as f:
                        data = json.load(f)
                    chats.append({
                        "id": data.get("id"),
                        "title": data.get("title"),
                        "created_at": data.get("created_at"),
                        "messages_count": len(data.get("messages", []))
                    })
                except:
                    pass

        if not chats:
            return "No hay chats compartidos"

        chats.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        lines = [f"📋 Chats compartidos ({len(chats)}):\n"]
        for c in chats:
            url = f"{CHAT_SHARE_URL}/chat/{c['id']}"
            lines.append(f"  📝 {c['title']}")
            lines.append(f"     {c['messages_count']} mensajes | {c['created_at'][:10]}")
            lines.append(f"     🔗 {url}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        return f"Error listando chats: {e}"


def tool_chat_get_shared(chat_id: str) -> str:
    try:
        filepath = os.path.join(CHAT_SHARE_DIR, f"{chat_id}.json")
        if not os.path.exists(filepath):
            return f"Error: Chat no encontrado: {chat_id}"

        with open(filepath) as f:
            data = json.load(f)

        lines = [f"📝 {data.get('title', 'Chat')}\n"]
        lines.append(f"📅 {data.get('created_at', 'N/A')[:19]}")
        lines.append(f"💬 {len(data.get('messages', []))} mensajes\n")

        for msg in data.get("messages", []):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:200]
            icon = "👤" if role == "user" else "🤖"
            lines.append(f"{icon} {role}: {content}")

        url = f"{CHAT_SHARE_URL}/chat/{chat_id}"
        lines.append(f"\n🔗 Enlace: {url}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error obteniendo chat: {e}"


E4B_URL = "http://localhost:9091/v1/chat/completions"
E4B_MODEL = "/home/darkseid/llama.cpp/ai-models/google_gemma-4-E4B-it-Q4_K_M.gguf"


def tool_delegate_to_subagent(query: str) -> str:
    try:
        payload = {
            "model": E4B_MODEL,
            "messages": [{"role": "user", "content": query}],
            "tools": [
                {"type": "function", "function": {"name": "spotify_search", "description": "Busca en Spotify", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                {"type": "function", "function": {"name": "spotify_play_track", "description": "Reproduce una canción", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                {"type": "function", "function": {"name": "spotify_play_artist", "description": "Reproduce un artista", "parameters": {"type": "object", "properties": {"artist": {"type": "string"}}, "required": ["artist"]}}},
                {"type": "function", "function": {"name": "spotify_now", "description": "Ver qué suena", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "spotify_play", "description": "Reanudar", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "spotify_pause", "description": "Pausar", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "spotify_next", "description": "Siguiente", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "spotify_previous", "description": "Anterior", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "get_plugs_status", "description": "Estado de enchufes Kasa", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "set_plug_state", "description": "Encender/apagar enchufe", "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}, "turn_on": {"type": "boolean"}}, "required": ["device_name", "turn_on"]}}}
            ],
            "max_tokens": 500
        }

        response = subprocess.run(
            ["curl", "-s", "-X", "POST", E4B_URL,
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=60
        )

        if response.returncode != 0:
            return f"Error conectando al sub-agente: {response.stderr}"

        data = json.loads(response.stdout)
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")

        if tool_calls:
            tc = tool_calls[0]
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])

            if fn_name == "spotify_search":
                result = tool_spotify_search(fn_args.get("query", ""))
            elif fn_name == "spotify_play_track":
                result = tool_spotify_play_track(fn_args.get("query", ""))
            elif fn_name == "spotify_play_artist":
                result = tool_spotify_play_artist(fn_args.get("artist", ""))
            elif fn_name == "spotify_now":
                result = tool_spotify_now()
            elif fn_name == "spotify_play":
                result = tool_spotify_play()
            elif fn_name == "spotify_pause":
                result = tool_spotify_pause()
            elif fn_name == "spotify_next":
                result = tool_spotify_next()
            elif fn_name == "spotify_previous":
                result = tool_spotify_previous()
            elif fn_name == "get_plugs_status":
                result = asyncio.run(kasa_get_plugs_status())
            elif fn_name == "set_plug_state":
                result = asyncio.run(kasa_set_plug_state(
                    fn_args.get("device_name", ""),
                    fn_args.get("turn_on", False)
                ))
            else:
                result = f"Tool desconocido: {fn_name}"

            log_operation("delegate_to_subagent", {"query": query}, f"{fn_name}: {result[:100]}")
            return f"[Sub-agente E4B] {result}"

        log_operation("delegate_to_subagent", {"query": query}, content[:100])
        return f"[Sub-agente E4B] {content}"

    except json.JSONDecodeError:
        return "Error parseando respuesta del sub-agente"
    except subprocess.TimeoutExpired:
        return "Timeout: el sub-agente tardó demasiado"
    except Exception as e:
        return f"Error delegando al sub-agente: {e}"


# ── Email Implementations ──────────────────────────────────
def tool_email_send(to: str, subject: str, body: str, cc: str = None, bcc: str = None, html: bool = False, attachments: list = None) -> str:
    try:
        # Build email headers
        headers = []
        headers.append(f"To: {to}")
        if cc:
            headers.append(f"Cc: {cc}")
        headers.append(f"Subject: {subject}")
        headers.append("MIME-Version: 1.0")
        
        if html:
            headers.append("Content-Type: text/html; charset=UTF-8")
        else:
            headers.append("Content-Type: text/plain; charset=UTF-8")
        
        if attachments:
            boundary = f"----=_Part_{int(time.time())}"
            headers.append(f"Multipart/mixed; boundary=\"{boundary}\"")
        
        email_content = "\r\n".join(headers) + "\r\n\r\n" + body
        
        # Add attachments
        if attachments:
            for filepath in attachments:
                filepath = os.path.expanduser(filepath)
                if os.path.exists(filepath):
                    import base64
                    filename = os.path.basename(filepath)
                    with open(filepath, "rb") as f:
                        file_data = base64.b64encode(f.read()).decode()
                    
                    attachment = f"\r\n--{boundary}\r\n"
                    attachment += f"Content-Type: application/octet-stream; name=\"{filename}\"\r\n"
                    attachment += "Content-Transfer-Encoding: base64\r\n"
                    attachment += f"Content-Disposition: attachment; filename=\"{filename}\"\r\n\r\n"
                    attachment += file_data
                    email_content += attachment
            
            email_content += f"\r\n--{boundary}--\r\n"
        
        # Write to temp file
        temp_file = f"/tmp/email_{int(time.time())}.eml"
        with open(temp_file, "w") as f:
            f.write(email_content)
        
        # Send with msmtp
        result = subprocess.run(
            ["msmtp", "-t"],
            input=email_content,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        # Cleanup
        os.remove(temp_file)
        
        if result.returncode == 0:
            log_operation("email_send", {"to": to, "subject": subject}, "OK")
            return f"Correo enviado a {to}"
        else:
            return f"Error enviando correo: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"


def tool_email_configure(smtp_host: str, username: str, password: str, from_email: str, smtp_port: int = 587, from_name: str = None, tls: bool = True) -> str:
    try:
        home = os.path.expanduser("~")
        config_path = os.path.join(home, ".msmtprc")
        
        # Build config
        config = f"""account default
host {smtp_host}
port {smtp_port}
auth on
user {username}
password {password}
"""
        
        if tls:
            config += "tls on\ntls_starttls on\n"
        
        if from_name and from_email:
            config += f"from {from_email}\n"
        
        # Write config
        with open(config_path, "w") as f:
            f.write(config)
        
        # Set permissions
        os.chmod(config_path, 0o600)
        
        # Save to DB
        try:
            import sqlite3
            db_path = os.path.join(home, ".config/ai-memory.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO access_credentials (name, credential_type, host, port, username, password_encrypted, extra_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("default_smtp", "smtp", smtp_host, smtp_port, username, password, 
                  json.dumps({"from_name": from_name, "from_email": from_email, "tls": tls})))
            conn.commit()
            conn.close()
        except Exception as db_err:
            pass
        
        log_operation("email_configure", {"host": smtp_host}, "OK")
        return f"SMTP configurado: {smtp_host}:{smtp_port}"
    
    except Exception as e:
        return f"Error configurando SMTP: {e}"


def tool_email_test(to: str = None) -> str:
    try:
        home = os.path.expanduser("~")
        config_path = os.path.join(home, ".msmtprc")
        
        if not os.path.exists(config_path):
            return "Error: No hay configuración SMTP. Usa email_configure primero."
        
        # Read from email from config
        from_email = None
        with open(config_path, "r") as f:
            for line in f:
                if line.startswith("from "):
                    from_email = line.split(" ", 1)[1].strip()
        
        if not to:
            to = from_email
        
        if not to:
            return "Error: No se pudo determinar el destinatario."
        
        return tool_email_send(
            to=to,
            subject="Test de correo - AI Lab",
            body="Este es un correo de prueba desde tu sistema de IA local.\n\nSi lo recibes, la configuración SMTP funciona correctamente."
        )
    
    except Exception as e:
        return f"Error: {e}"


# ── Communication Implementations ──────────────────────────
def _discover_mx_records(domain: str) -> list:
    """Discover MX records for a domain."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = []
        for rdata in answers:
            mx_records.append({
                "host": str(rdata.exchange).rstrip('.'),
                "priority": rdata.preference
            })
        mx_records.sort(key=lambda x: x["priority"])
        return mx_records
    except Exception:
        return []


def _probe_smtp(host: str, ports: list = [587, 465, 25]) -> dict:
    """Probe SMTP server for supported ports and TLS."""
    import socket
    
    for port in ports:
        try:
            sock = socket.create_connection((host, port), timeout=5)
            banner = sock.recv(1024).decode('utf-8', errors='ignore')
            
            if port == 465:
                # SSL port
                sock.close()
                return {"port": port, "tls": True, "ssl": True, "banner": banner.strip()}
            else:
                # Try STARTTLS
                sock.send(b"EHLO test\r\n")
                sock.recv(1024)
                sock.send(b"STARTTLS\r\n")
                resp = sock.recv(1024).decode('utf-8', errors='ignore')
                sock.close()
                
                if "220" in resp:
                    return {"port": port, "tls": True, "ssl": False, "banner": banner.strip()}
                else:
                    return {"port": port, "tls": False, "ssl": False, "banner": banner.strip()}
        except Exception:
            continue
    
    return None


def tool_email_discover_settings(email: str) -> str:
    """Auto-discover SMTP settings for an email domain."""
    try:
        # Extract domain
        if "@" in email:
            domain = email.split("@")[1]
        else:
            domain = email
        
        # Discover MX records
        mx_records = _discover_mx_records(domain)
        
        if not mx_records:
            return f"No se encontraron MX records para {domain}"
        
        result = f"📧 Configuración descubierta para {domain}:\n\n"
        result += "MX Records:\n"
        
        best_smtp = None
        
        for mx in mx_records:
            result += f"  • {mx['host']} (prioridad: {mx['priority']})\n"
            
            # Probe the first MX server
            if not best_smtp:
                probe = _probe_smtp(mx["host"])
                if probe:
                    best_smtp = {
                        "host": mx["host"],
                        "port": probe["port"],
                        "tls": probe["tls"],
                        "ssl": probe.get("ssl", False)
                    }
        
        if best_smtp:
            result += f"\n✅ SMTP detectado:\n"
            result += f"  Host: {best_smtp['host']}\n"
            result += f"  Puerto: {best_smtp['port']}\n"
            result += f"  TLS: {'Sí' if best_smtp['tls'] else 'No'}\n"
            result += f"  SSL: {'Sí' if best_smtp['ssl'] else 'No'}\n"
        else:
            result += "\n⚠️ No se pudo detectar SMTP automáticamente"
        
        return result
    
    except Exception as e:
        return f"Error descubriendo configuración: {e}"


def tool_email_setup_wizard(email: str, password: str, display_name: str = None) -> str:
    """Complete email setup wizard: discover, configure, save, test."""
    try:
        import sqlite3
        
        # Extract domain and username
        if "@" not in email:
            return "Error: Se requiere un email completo (ej: user@gmail.com)"
        
        username = email.split("@")[0]
        domain = email.split("@")[1]
        
        result = f"🔧 Wizard de configuración para {email}\n\n"
        
        # Step 1: Discover SMTP settings
        result += "1️⃣ Descubriendo configuración SMTP...\n"
        mx_records = _discover_mx_records(domain)
        
        if not mx_records:
            return result + "❌ No se encontraron MX records. Configura manualmente con email_configure."
        
        smtp_host = mx_records[0]["host"]
        probe = _probe_smtp(smtp_host)
        
        if not probe:
            return result + "❌ No se pudo detectar el servidor SMTP."
        
        smtp_port = probe["port"]
        tls = probe["tls"]
        
        result += f"  ✅ SMTP: {smtp_host}:{smtp_port}\n"
        result += f"  ✅ TLS: {'Sí' if tls else 'No'}\n\n"
        
        # Step 2: Configure msmtp
        result += "2️⃣ Configurando msmtp...\n"
        
        home = os.path.expanduser("~")
        config_path = os.path.join(home, ".msmtprc")
        
        config = f"""account default
host {smtp_host}
port {smtp_port}
auth on
user {email}
password {password}
"""
        if tls:
            if probe.get("ssl"):
                config += "tls on\n"
            else:
                config += "tls on\ntls_starttls on\n"
        
        config += f"from {email}\n"
        
        with open(config_path, "w") as f:
            f.write(config)
        os.chmod(config_path, 0o600)
        
        result += "  ✅ msmtp configurado\n\n"
        
        # Step 3: Save to DB (encrypted)
        result += "3️⃣ Guardando en base de datos...\n"
        
        encrypted_password = encrypt_value(password)
        
        db_path = os.path.join(home, ".config/ai-memory.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute("SELECT id FROM access_credentials WHERE name = ?", (f"smtp_{domain}",))
        existing = cursor.fetchone()
        
        extra_data = json.dumps({
            "email": email,
            "display_name": display_name or username,
            "tls": tls,
            "ssl": probe.get("ssl", False)
        })
        
        if existing:
            cursor.execute("""
                UPDATE access_credentials 
                SET host=?, port=?, username=?, password_encrypted=?, extra_data=?, updated_at=CURRENT_TIMESTAMP
                WHERE name=?
            """, (smtp_host, smtp_port, email, encrypted_password, extra_data, f"smtp_{domain}"))
        else:
            cursor.execute("""
                INSERT INTO access_credentials (name, credential_type, host, port, username, password_encrypted, extra_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (f"smtp_{domain}", "smtp", smtp_host, smtp_port, email, encrypted_password, extra_data))
        
        conn.commit()
        conn.close()
        
        result += "  ✅ Credenciales guardadas (encriptadas)\n\n"
        
        # Step 4: Test
        result += "4️⃣ Probando conexión...\n"
        
        test_result = tool_email_test(email)
        
        if "enviado" in test_result.lower() or "ok" in test_result.lower():
            result += f"  ✅ {test_result}\n\n"
            result += f"🎉 ¡Configuración completada!\n"
            result += f"   Email: {email}\n"
            result += f"   SMTP: {smtp_host}:{smtp_port}\n"
            result += f"   Puedes usar email_send para enviar correos."
        else:
            result += f"  ⚠️ {test_result}\n\n"
            result += "La configuración se guardó pero hubo un error en la prueba."
        
        return result
    
    except Exception as e:
        return f"Error en wizard: {e}"


def _format_whatsapp_element(element: dict, indent: int = 0) -> str:
    """Format a single WhatsApp element."""
    etype = element.get("type", "text")
    text = element.get("text", "")
    items = element.get("items", [])
    url = element.get("url", "")
    name = element.get("name", "")
    
    prefix = "  " * indent
    
    if etype == "heading":
        return f"*{text}*"
    elif etype == "bold":
        return f"*{text}*"
    elif etype == "italic":
        return f"_{text}_"
    elif etype == "strikethrough":
        return f"~{text}~"
    elif etype == "code":
        return f"```{text}```"
    elif etype == "text":
        return f"{prefix}{text}"
    elif etype == "emoji":
        # Common emoji names to unicode
        emojis = {
            "check": "✅", "x": "❌", "warning": "⚠️", "star": "⭐",
            "heart": "❤️", "fire": "🔥", "rocket": "🚀", "thumbsup": "👍",
            "clap": "👏", "wave": "👋", "sad": "😢", "happy": "😊",
            "think": "🤔", "eyes": "👀", "100": "💯", "tada": "🎉",
            "bulb": "💡", "lock": "🔒", "unlock": "🔓", "bell": "🔔",
            "mail": "📧", "phone": "📞", "calendar": "📅", "clock": "⏰",
            "gear": "⚙️", "wrench": "🔧", "hammer": "🔨", "key": "🔑",
            "house": "🏠", "building": "🏢", "globe": "🌍", "link": "🔗",
            "paperclip": "📎", "memo": "📝", "book": "📖", "lightning": "⚡"
        }
        emoji_char = emojis.get(name.lower(), f"[{name}]")
        return f"{emoji_char}"
    elif etype == "link":
        if text:
            return f"{text}: {url}"
        return url
    elif etype == "list":
        bullets = ["•", "◦", "▪"]
        result = []
        for i, item in enumerate(items):
            if isinstance(item, dict):
                item_text = item.get("text", "")
                sub_items = item.get("items", [])
                bullet = bullets[min(indent, len(bullets) - 1)]
                result.append(f"{prefix}{bullet} {item_text}")
                if sub_items:
                    for sub in sub_items:
                        if isinstance(sub, dict):
                            result.append(_format_whatsapp_element(sub, indent + 1))
                        else:
                            sub_bullet = bullets[min(indent + 1, len(bullets) - 1)]
                            result.append(f"{prefix}  {sub_bullet} {sub}")
            else:
                bullet = bullets[min(indent, len(bullets) - 1)]
                result.append(f"{prefix}{bullet} {item}")
        return "\n".join(result)
    elif etype == "newline":
        return ""
    elif etype == "divider":
        return "─────────────────"
    else:
        return f"{prefix}{text}"


def tool_format_whatsapp(elements: list, copy_to_clipboard: bool = True) -> str:
    """Format text for WhatsApp with rich formatting."""
    try:
        lines = []
        for element in elements:
            formatted = _format_whatsapp_element(element)
            lines.append(formatted)
        
        result = "\n".join(lines)
        
        if copy_to_clipboard:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=result.encode(),
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                pass
        
        log_operation("format_whatsapp", {"elements_count": len(elements)}, result[:100])
        return result
    
    except Exception as e:
        return f"Error formateando: {e}"


def tool_whatsapp_link(phone: str, message: str, copy_to_clipboard: bool = True) -> str:
    """Generate WhatsApp link with pre-filled message."""
    try:
        # Clean phone number (remove spaces, dashes, plus)
        clean_phone = phone.replace(" ", "").replace("-", "").replace("+", "").replace("(", "").replace(")", "")
        
        # Ensure it starts with country code
        if not clean_phone.startswith("52") and len(clean_phone) == 10:
            clean_phone = "52" + clean_phone
        
        # URL encode the message
        encoded_message = quote(message)
        
        # Generate link
        link = f"https://wa.me/{clean_phone}?text={encoded_message}"
        
        if copy_to_clipboard:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=link.encode(),
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                pass
        
        result = f"📱 Enlace de WhatsApp:\n{link}\n\n"
        result += f"📞 Teléfono: {clean_phone}\n"
        result += f"💬 Mensaje: {message[:50]}{'...' if len(message) > 50 else ''}"
        
        log_operation("whatsapp_link", {"phone": clean_phone}, link)
        return result
    
    except Exception as e:
        return f"Error generando enlace: {e}"


def tool_format_email(to: str = None, subject: str = None, greeting: str = None, 
                      body: str = "", bullets: list = None, signature: str = None,
                      format: str = "both", copy_to_clipboard: bool = False) -> str:
    """Compose email body with formatting."""
    try:
        result = {}
        
        # Build greeting
        if greeting:
            saludo = greeting
        elif to:
            saludo = f"Hola {to},"
        else:
            saludo = ""
        
        # Build plain text version
        plain_lines = []
        if saludo:
            plain_lines.append(saludo)
            plain_lines.append("")
        
        plain_lines.append(body)
        
        if bullets:
            plain_lines.append("")
            for bullet in bullets:
                plain_lines.append(f"• {bullet}")
        
        if signature:
            plain_lines.append("")
            plain_lines.append(signature)
        
        plain_text = "\n".join(plain_lines)
        
        # Build HTML version
        html_lines = []
        if saludo:
            html_lines.append(f"<p>{saludo}</p>")
        
        html_lines.append(f"<p>{body}</p>")
        
        if bullets:
            html_lines.append("<ul>")
            for bullet in bullets:
                html_lines.append(f"<li>{bullet}</li>")
            html_lines.append("</ul>")
        
        if signature:
            html_lines.append(f"<p style='color: #666; margin-top: 20px;'>{signature.replace(chr(10), '<br>')}</p>")
        
        html_text = "\n".join(html_lines)
        
        # Prepare output
        if format == "plain":
            result_text = plain_text
        elif format == "html":
            result_text = html_text
        else:  # both
            result_text = f"=== PLAIN TEXT ===\n{plain_text}\n\n=== HTML ===\n{html_text}"
        
        if copy_to_clipboard:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=plain_text.encode(),
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                pass
        
        log_operation("format_email", {"to": to, "format": format}, result_text[:100])
        return result_text
    
    except Exception as e:
        return f"Error formateando email: {e}"
def _parse_ssh_config() -> dict:
    """Parse ~/.ssh/config into a dict of host aliases."""
    ssh_config_path = os.path.expanduser("~/.ssh/config")
    hosts = {}
    
    if not os.path.exists(ssh_config_path):
        return hosts
    
    current_host = None
    with open(ssh_config_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if line.lower().startswith("host "):
                current_host = line.split(None, 1)[1]
                hosts[current_host] = {"hostname": current_host, "user": "darkseid", "port": 22}
            elif current_host:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    key = parts[0].lower()
                    value = parts[1]
                    if key == "hostname":
                        hosts[current_host]["hostname"] = value
                    elif key == "user":
                        hosts[current_host]["user"] = value
                    elif key == "port":
                        hosts[current_host]["port"] = int(value)
                    elif key == "identityfile":
                        hosts[current_host]["identity_file"] = value
    
    return hosts


def _resolve_host(host: str) -> dict:
    """Resolve host alias or return direct connection info."""
    hosts = _parse_ssh_config()
    
    if host in hosts:
        return hosts[host]
    
    # Direct IP/hostname
    return {"hostname": host, "user": "darkseid", "port": 22}


def tool_ssh_connect(host: str, command: str, user: str = None, port: int = 22, timeout: int = 30) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_port = port or host_info.get("port", 22)
        ssh_hostname = host_info.get("hostname", host)
        
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-p", str(ssh_port), f"{ssh_user}@{ssh_hostname}", command]
        
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr] {result.stderr}"
        
        log_operation("ssh_connect", {"host": host, "command": command}, f"exit:{result.returncode}")
        return f"[exit:{result.returncode}] {output.strip()}"
    
    except subprocess.TimeoutExpired:
        return f"Error: Timeout ({timeout}s) conectando a {host}"
    except Exception as e:
        return f"Error SSH: {e}"


def tool_ssh_copy(host: str, local_path: str, remote_path: str, user: str = None, port: int = 22) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_port = port or host_info.get("port", 22)
        ssh_hostname = host_info.get("hostname", host)
        
        local_path = os.path.expanduser(local_path)
        
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-P", str(ssh_port), local_path, f"{ssh_user}@{ssh_hostname}:{remote_path}"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            log_operation("ssh_copy", {"host": host, "local": local_path, "remote": remote_path}, "OK")
            return f"Archivo copiado a {host}:{remote_path}"
        else:
            return f"Error SCP: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"


def tool_ssh_fetch(host: str, remote_path: str, local_path: str, user: str = None, port: int = 22) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_port = port or host_info.get("port", 22)
        ssh_hostname = host_info.get("hostname", host)
        
        local_path = os.path.expanduser(local_path)
        
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-P", str(ssh_port), f"{ssh_user}@{ssh_hostname}:{remote_path}", local_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            log_operation("ssh_fetch", {"host": host, "remote": remote_path, "local": local_path}, "OK")
            return f"Archivo descargado a {local_path}"
        else:
            return f"Error SCP: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"


def tool_ssh_sync(host: str, local_path: str, remote_path: str, user: str = None, port: int = 22, delete: bool = False, exclude: list = None) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_port = port or host_info.get("port", 22)
        ssh_hostname = host_info.get("hostname", host)
        
        local_path = os.path.expanduser(local_path)
        
        rsync_cmd = ["rsync", "-avz", "-e", f"ssh -o StrictHostKeyChecking=no -p {ssh_port}"]
        
        if delete:
            rsync_cmd.append("--delete")
        
        if exclude:
            for pattern in exclude:
                rsync_cmd.extend(["--exclude", pattern])
        
        rsync_cmd.extend([f"{local_path}/", f"{ssh_user}@{ssh_hostname}:{remote_path}/"])
        
        result = subprocess.run(
            rsync_cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            log_operation("ssh_sync", {"host": host, "local": local_path, "remote": remote_path}, "OK")
            return f"Sincronizado: {local_path} → {host}:{remote_path}"
        else:
            return f"Error rsync: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"


def tool_ssh_tunnel(host: str, local_port: int, remote_port: int, user: str = None, ssh_port: int = 22, background: bool = True) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_hostname = host_info.get("hostname", host)
        
        ssh_cmd = f"ssh -o StrictHostKeyChecking=no -p {ssh_port} -L {local_port}:localhost:{remote_port} {ssh_user}@{ssh_hostname}"
        
        if background:
            # Use autossh for persistent tunnel
            autossh_cmd = f"autossh -M 0 -f -N {ssh_cmd}"
            result = subprocess.run(
                autossh_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                log_operation("ssh_tunnel", {"host": host, "local_port": local_port, "remote_port": remote_port}, "OK")
                return f"Túnel creado: localhost:{local_port} → {host}:{remote_port}"
            else:
                return f"Error túnel: {result.stderr}"
        else:
            # Interactive
            subprocess.run(ssh_cmd, shell=True, timeout=30)
            return "Túnel cerrado"
    
    except Exception as e:
        return f"Error: {e}"


def tool_ssh_list_hosts() -> str:
    try:
        hosts = _parse_ssh_config()
        
        if not hosts:
            return "No hay hosts configurados en ~/.ssh/config"
        
        result = "Hosts SSH configurados:\n"
        for name, info in hosts.items():
            result += f"  {name}: {info.get('user', 'darkseid')}@{info.get('hostname', '?')}:{info.get('port', 22)}\n"
        
        return result
    
    except Exception as e:
        return f"Error: {e}"


def tool_ssh_add_host(hostname: str, host: str, user: str = "darkseid", port: int = 22, identity_file: str = None) -> str:
    try:
        ssh_config_path = os.path.expanduser("~/.ssh/config")
        
        # Check if host already exists
        hosts = _parse_ssh_config()
        if hostname in hosts:
            return f"Error: Host '{hostname}' ya existe. Usa ssh_config para editarlo."
        
        # Build config entry
        entry = f"\nHost {hostname}\n"
        entry += f"    HostName {host}\n"
        entry += f"    User {user}\n"
        entry += f"    Port {port}\n"
        if identity_file:
            entry += f"    IdentityFile {identity_file}\n"
        entry += "    StrictHostKeyChecking no\n"
        
        # Append to config
        with open(ssh_config_path, "a") as f:
            f.write(entry)
        
        log_operation("ssh_add_host", {"hostname": hostname, "host": host}, "OK")
        return f"Host '{hostname}' agregado a ~/.ssh/config"
    
    except Exception as e:
        return f"Error: {e}"


def tool_ssh_status(host: str) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_hostname = host_info.get("hostname", host)
        ssh_port = host_info.get("port", 22)
        
        # Ping
        ping_result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ssh_hostname],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        ping_ok = ping_result.returncode == 0
        
        # SSH port check
        ssh_result = subprocess.run(
            ["nc", "-z", "-w", "2", ssh_hostname, str(ssh_port)],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        ssh_ok = ssh_result.returncode == 0
        
        status = f"Host: {ssh_hostname}:{ssh_port}\n"
        status += f"Ping: {'OK' if ping_ok else 'FALLA'}\n"
        status += f"SSH:  {'OK' if ssh_ok else 'FALLA'}\n"
        
        if ping_ok and ssh_ok:
            status += "Estado: ONLINE"
        elif ping_ok:
            status += "Estado: SSH bloqueado"
        else:
            status += "Estado: OFFLINE"
        
        return status
    
    except Exception as e:
        return f"Error: {e}"


# ── Web & Internet Implementations ─────────────────────────
def tool_browse_web(url: str, format: str = "text", timeout: int = 30) -> str:
    """Fetch URL content."""
    try:
        import httpx
        
        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }
        
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()
        
        if format == "json":
            try:
                data = response.json()
                return json.dumps(data, indent=2, ensure_ascii=False)
            except:
                return f"No es JSON válido:\n{response.text[:2000]}"
        
        elif format == "html":
            return response.text[:5000]
        
        else:  # text
            # Simple HTML to text
            import re
            text = response.text
            # Remove scripts and styles
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Clean whitespace
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:3000]
    
    except Exception as e:
        return f"Error obteniendo URL: {e}"


def tool_http_request(url: str, method: str = "GET", headers: dict = None, body: str = None, timeout: int = 30) -> str:
    """Make HTTP request."""
    try:
        import httpx
        
        req_headers = headers or {}
        
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            if method == "GET":
                response = client.get(url, headers=req_headers)
            elif method == "POST":
                response = client.post(url, headers=req_headers, content=body)
            elif method == "PUT":
                response = client.put(url, headers=req_headers, content=body)
            elif method == "DELETE":
                response = client.delete(url, headers=req_headers)
            elif method == "PATCH":
                response = client.patch(url, headers=req_headers, content=body)
            else:
                return f"Método no soportado: {method}"
            
            result = {
                "status": response.status_code,
                "headers": dict(response.headers),
                "body": response.text[:5000]
            }
            
            log_operation("http_request", {"url": url, "method": method}, f"status:{response.status_code}")
            return json.dumps(result, indent=2, ensure_ascii=False)
    
    except Exception as e:
        return f"Error HTTP: {e}"


def tool_search_news(query: str, region: str = "wt-wt", time: str = "w", max_results: int = 10) -> str:
    """Search news via DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            results = list(ddgs.news(query, region=region, timelimit=time, max_results=max_results))
        
        if not results:
            return "No se encontraron noticias."
        
        output = f"Noticias para '{query}':\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. **{r.get('title', 'N/A')}**\n"
            output += f"   Fuente: {r.get('source', 'N/A')}\n"
            output += f"   Fecha: {r.get('date', 'N/A')}\n"
            output += f"   URL: {r.get('url', 'N/A')}\n\n"
        
        return output
    
    except Exception as e:
        return f"Error buscando noticias: {e}"


def tool_search_docs(query: str, language: str = None, max_results: int = 5) -> str:
    """Search technical documentation."""
    try:
        from duckduckgo_search import DDGS
        
        search_query = query
        if language:
            search_query = f"{language} {query} documentation"
        
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=max_results))
        
        if not results:
            return "No se encontró documentación."
        
        output = f"Documentación para '{query}':\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. **{r.get('title', 'N/A')}**\n"
            output += f"   {r.get('body', 'N/A')[:200]}\n"
            output += f"   URL: {r.get('href', 'N/A')}\n\n"
        
        return output
    
    except Exception as e:
        return f"Error buscando docs: {e}"


def tool_dns_lookup(domain: str, record_type: str = "ALL") -> str:
    """DNS lookup."""
    try:
        import dns.resolver
        
        record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA"]
        if record_type != "ALL":
            record_types = [record_type]
        
        output = f"DNS para {domain}:\n\n"
        
        for rtype in record_types:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                output += f"📋 {rtype}:\n"
                for rdata in answers:
                    output += f"  • {rdata}\n"
                output += "\n"
            except dns.resolver.NoAnswer:
                pass
            except dns.resolver.NXDOMAIN:
                return f"Error: Dominio {domain} no existe"
            except Exception:
                pass
        
        return output if output.strip() != f"DNS para {domain}:" else "No se encontraron registros"
    
    except ImportError:
        return "Error: dnspython no instalado"
    except Exception as e:
        return f"Error DNS: {e}"


def tool_ssl_check(domain: str) -> str:
    """Check SSL certificate."""
    try:
        import ssl
        import socket
        from datetime import datetime
        
        context = ssl.create_default_context()
        
        with socket.create_connection((domain, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
        
        # Parse dates
        not_before = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y %Z')
        not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
        days_left = (not_after - datetime.now()).days
        
        output = f"🔒 SSL para {domain}:\n\n"
        output += f"  Emisor: {dict(x[0] for x in cert['issuer']).get('commonName', 'N/A')}\n"
        output += f"  Válido desde: {not_before.strftime('%Y-%m-%d')}\n"
        output += f"  Válido hasta: {not_after.strftime('%Y-%m-%d')}\n"
        output += f"  Días restantes: {days_left}\n"
        output += f"  Dominios: {', '.join(cert.get('subjectAltName', [('*', )])[0][1] if cert.get('subjectAltName') else [domain])}\n"
        
        if days_left < 30:
            output += f"\n⚠️ ¡Certificado expira en {days_left} días!"
        else:
            output += f"\n✅ Certificado válido"
        
        return output
    
    except Exception as e:
        return f"Error verificando SSL: {e}"


def tool_whois_lookup(domain: str) -> str:
    """WHOIS lookup."""
    try:
        import whois
        
        w = whois.whois(domain)
        
        output = f"📋 WHOIS para {domain}:\n\n"
        
        if w.domain_name:
            output += f"  Dominio: {w.domain_name}\n"
        if w.registrar:
            output += f"  Registrar: {w.registrar}\n"
        if w.creation_date:
            output += f"  Creado: {w.creation_date}\n"
        if w.expiration_date:
            output += f"  Expira: {w.expiration_date}\n"
        if w.name_servers:
            output += f"  Name Servers: {', '.join(w.name_servers[:3])}\n"
        if w.org:
            output += f"  Organización: {w.org}\n"
        if w.country:
            output += f"  País: {w.country}\n"
        
        return output
    
    except ImportError:
        return "Error: python-whois no instalado"
    except Exception as e:
        return f"Error WHOIS: {e}"


# ── Database Implementations ────────────────────────────────
def tool_sql_query(query: str, database: str = None, params: list = None) -> str:
    """Execute SQL query on SQLite database."""
    try:
        import sqlite3
        
        if not database:
            database = os.path.join(HOME, ".config/ai-memory.db")
        else:
            database = os.path.expanduser(database)
        
        if not os.path.exists(database):
            return f"Error: Base de datos no existe: {database}"
        
        conn = sqlite3.connect(database)
        cursor = conn.cursor()
        
        # Check if it's a SELECT query
        is_select = query.strip().upper().startswith("SELECT")
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if is_select:
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            
            if not rows:
                return "Query ejecutada. Sin resultados."
            
            output = f"Resultados ({len(rows)} filas):\n\n"
            
            # Header
            output += " | ".join(columns) + "\n"
            output += "-" * 50 + "\n"
            
            # Rows
            for row in rows[:100]:  # Limit to 100 rows
                output += " | ".join(str(v) if v is not None else "NULL" for v in row) + "\n"
            
            if len(rows) > 100:
                output += f"\n... y {len(rows) - 100} filas más"
            
            return output
        else:
            conn.commit()
            affected = cursor.rowcount
            log_operation("sql_query", {"query": query[:100]}, f"affected:{affected}")
            return f"Query ejecutada. Filas afectadas: {affected}"
        
        conn.close()
    
    except Exception as e:
        return f"Error SQL: {e}"


def tool_backup_database(database: str, backup_path: str = None) -> str:
    """Backup SQLite database."""
    try:
        import sqlite3
        import shutil
        
        database = os.path.expanduser(database)
        
        if not os.path.exists(database):
            return f"Error: Base de datos no existe: {database}"
        
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db_name = os.path.basename(database).replace(".db", "")
            backup_dir = os.path.join(HOME, ".local/backups")
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"{db_name}_{timestamp}.db")
        else:
            backup_path = os.path.expanduser(backup_path)
        
        # Use SQLite backup API
        source = sqlite3.connect(database)
        dest = sqlite3.connect(backup_path)
        source.backup(dest)
        source.close()
        dest.close()
        
        size = os.path.getsize(backup_path)
        log_operation("backup_database", {"database": database}, f"backup:{backup_path}")
        return f"Backup creado: {backup_path} ({size} bytes)"
    
    except Exception as e:
        return f"Error creando backup: {e}"


# ── Data Processing Implementations ─────────────────────────
def tool_csv_to_json(input_file: str, output_file: str = None) -> str:
    """Convert CSV to JSON."""
    try:
        import csv
        
        input_file = os.path.expanduser(input_file)
        
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
        
        if not output_file:
            output_file = input_file.rsplit('.', 1)[0] + '.json'
        else:
            output_file = os.path.expanduser(output_file)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        log_operation("csv_to_json", {"input": input_file}, f"output:{output_file}")
        return f"Convertido: {output_file} ({len(data)} registros)"
    
    except Exception as e:
        return f"Error convirtiendo: {e}"


def tool_json_to_csv(input_file: str, output_file: str = None) -> str:
    """Convert JSON to CSV."""
    try:
        import csv
        
        input_file = os.path.expanduser(input_file)
        
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list) or not data:
            return "Error: JSON debe ser un array de objetos"
        
        if not output_file:
            output_file = input_file.rsplit('.', 1)[0] + '.csv'
        else:
            output_file = os.path.expanduser(output_file)
        
        headers = data[0].keys()
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)
        
        log_operation("json_to_csv", {"input": input_file}, f"output:{output_file}")
        return f"Convertido: {output_file} ({len(data)} registros)"
    
    except Exception as e:
        return f"Error convirtiendo: {e}"


def tool_convert_file(input_file: str, output_format: str, output_file: str = None) -> str:
    """Convert between file formats."""
    try:
        import csv
        import xml.etree.ElementTree as ET
        import yaml
        
        input_file = os.path.expanduser(input_file)
        
        if not os.path.exists(input_file):
            return f"Error: Archivo no existe: {input_file}"
        
        # Read input
        ext = input_file.rsplit('.', 1)[-1].lower()
        
        with open(input_file, 'r', encoding='utf-8') as f:
            if ext == 'csv':
                data = list(csv.DictReader(f))
            elif ext == 'json':
                data = json.load(f)
            elif ext == 'xml':
                tree = ET.parse(f)
                root = tree.getroot()
                data = [{elem.tag: elem.text for elem in child} for child in root]
            elif ext == 'yaml' or ext == 'yml':
                data = yaml.safe_load(f)
            elif ext == 'md' or ext == 'txt':
                data = f.read()
            else:
                return f"Formato no soportado: {ext}"
        
        # Generate output
        if not output_file:
            output_file = input_file.rsplit('.', 1)[0] + '.' + output_format
        else:
            output_file = os.path.expanduser(output_file)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            if output_format == 'csv':
                if isinstance(data, list) and data:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
            elif output_format == 'json':
                json.dump(data, f, indent=2, ensure_ascii=False)
            elif output_format == 'xml':
                root = ET.Element("data")
                for item in data:
                    elem = ET.SubElement(root, "item")
                    for k, v in item.items():
                        child = ET.SubElement(elem, k)
                        child.text = str(v)
                ET.ElementTree(root).write(f, encoding='unicode')
            elif output_format == 'yaml':
                yaml.dump(data, f, allow_unicode=True)
            elif output_format == 'md':
                if isinstance(data, list) and data:
                    f.write("| " + " | ".join(data[0].keys()) + " |\n")
                    f.write("|" + "|".join(["---"] * len(data[0])) + "|\n")
                    for row in data:
                        f.write("| " + " | ".join(str(v) for v in row.values()) + " |\n")
            elif output_format == 'txt':
                f.write(str(data))
        
        log_operation("convert_file", {"input": input_file}, f"output:{output_file}")
        return f"Convertido: {output_file}"
    
    except Exception as e:
        return f"Error convirtiendo: {e}"


def tool_extract_pdf(pdf_path: str, pages: str = "all") -> str:
    """Extract text from PDF."""
    try:
        from PyPDF2 import PdfReader
        
        pdf_path = os.path.expanduser(pdf_path)
        
        if not os.path.exists(pdf_path):
            return f"Error: PDF no existe: {pdf_path}"
        
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        
        # Parse pages to extract
        if pages == "all":
            page_indices = range(total_pages)
        else:
            page_indices = []
            for part in pages.split(","):
                if "-" in part:
                    start, end = part.split("-")
                    page_indices.extend(range(int(start) - 1, int(end)))
                else:
                    page_indices.append(int(part) - 1)
        
        output = f"📄 PDF: {os.path.basename(pdf_path)} ({total_pages} páginas)\n\n"
        
        for i in page_indices:
            if i < total_pages:
                text = reader.pages[i].extract_text()
                output += f"--- Página {i + 1} ---\n{text}\n\n"
        
        return output[:5000]
    
    except ImportError:
        return "Error: PyPDF2 no instalado"
    except Exception as e:
        return f"Error extrayendo PDF: {e}"


def tool_generate_csv(data: str, output_file: str, delimiter: str = ",") -> str:
    """Generate CSV from JSON data."""
    try:
        import csv
        
        # Parse data
        if isinstance(data, str):
            rows = json.loads(data)
        else:
            rows = data
        
        if not isinstance(rows, list) or not rows:
            return "Error: Datos deben ser un array de objetos"
        
        output_file = os.path.expanduser(output_file)
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
        
        log_operation("generate_csv", {"rows": len(rows)}, f"output:{output_file}")
        return f"CSV generado: {output_file} ({len(rows)} filas)"
    
    except Exception as e:
        return f"Error generando CSV: {e}"


def tool_data_analysis(file_path: str, column: str = None) -> str:
    """Basic data analysis."""
    try:
        import csv
        
        file_path = os.path.expanduser(file_path)
        
        if not os.path.exists(file_path):
            return f"Error: Archivo no existe: {file_path}"
        
        ext = file_path.rsplit('.', 1)[-1].lower()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            if ext == 'csv':
                data = list(csv.DictReader(f))
            elif ext == 'json':
                data = json.load(f)
            else:
                return f"Formato no soportado: {ext}"
        
        if not data:
            return "Sin datos para analizar"
        
        output = f"📊 Análisis de {os.path.basename(file_path)}:\n\n"
        output += f"Total registros: {len(data)}\n"
        output += f"Columnas: {', '.join(data[0].keys())}\n\n"
        
        if column and column in data[0]:
            values = [row[column] for row in data if row.get(column)]
            
            # Try numeric analysis
            try:
                nums = [float(v) for v in values if v]
                output += f"📊 Análisis de '{column}':\n"
                output += f"  Min: {min(nums)}\n"
                output += f"  Max: {max(nums)}\n"
                output += f"  Promedio: {sum(nums) / len(nums):.2f}\n"
                output += f"  Valores únicos: {len(set(values))}\n"
            except ValueError:
                # Text analysis
                output += f"📊 Análisis de '{column}':\n"
                output += f"  Valores únicos: {len(set(values))}\n"
                from collections import Counter
                counts = Counter(values)
                output += f"  Más comunes: {counts.most_common(5)}\n"
        
        # Check for nulls
        nulls = sum(1 for row in data if any(not v for v in row.values()))
        output += f"\nRegistros con valores vacíos: {nulls}\n"
        
        return output
    
    except Exception as e:
        return f"Error analizando: {e}"


# ── Log & System Implementations ────────────────────────────
def tool_log_analysis(log_file: str, lines: int = 100, filter: str = None) -> str:
    """Analyze system logs."""
    try:
        log_file = os.path.expanduser(log_file)
        
        if not os.path.exists(log_file):
            return f"Error: Log no existe: {log_file}"
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        # Get last N lines
        log_lines = all_lines[-lines:]
        
        # Filter if specified
        if filter:
            log_lines = [l for l in log_lines if filter.upper() in l.upper()]
        
        output = f"📋 Análisis de {os.path.basename(log_file)}:\n\n"
        output += f"Líneas totales: {len(all_lines)}\n"
        output += f"Líneas analizadas: {len(log_lines)}\n\n"
        
        # Count by level
        from collections import Counter
        levels = Counter()
        for line in log_lines:
            if "ERROR" in line.upper():
                levels["ERROR"] += 1
            elif "WARN" in line.upper():
                levels["WARN"] += 1
            elif "INFO" in line.upper():
                levels["INFO"] += 1
            else:
                levels["OTHER"] += 1
        
        output += "Por nivel:\n"
        for level, count in levels.most_common():
            output += f"  {level}: {count}\n"
        
        # Show errors
        errors = [l.strip() for l in log_lines if "ERROR" in l.upper()]
        if errors:
            output += f"\nÚltimos errores:\n"
            for e in errors[:5]:
                output += f"  • {e[:200]}\n"
        
        return output
    
    except Exception as e:
        return f"Error analizando logs: {e}"


def tool_generate_report(title: str, sections: list, output_file: str = None) -> str:
    """Generate Markdown report."""
    try:
        output = f"# {title}\n\n"
        output += f"*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
        
        for section in sections:
            heading = section.get("heading", "")
            content = section.get("content", "")
            data = section.get("data", [])
            
            if heading:
                output += f"## {heading}\n\n"
            
            if content:
                output += f"{content}\n\n"
            
            if data:
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    # Table
                    headers = data[0].keys()
                    output += "| " + " | ".join(headers) + " |\n"
                    output += "|" + "|".join(["---"] * len(headers)) + "|\n"
                    for row in data:
                        output += "| " + " | ".join(str(v) for v in row.values()) + " |\n"
                    output += "\n"
                elif isinstance(data, list):
                    # List
                    for item in data:
                        output += f"- {item}\n"
                    output += "\n"
        
        if output_file:
            output_file = os.path.expanduser(output_file)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            return f"Reporte generado: {output_file}"
        
        return output
    
    except Exception as e:
        return f"Error generando reporte: {e}"


# ── Security Implementations ────────────────────────────────
def tool_security_audit(scope: str = "full") -> str:
    """Basic security audit."""
    try:
        output = "🔒 Auditoría de Seguridad\n\n"
        
        if scope in ["full", "ports"]:
            output += "📡 Puertos abiertos:\n"
            result = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split('\n')[1:]
            for line in lines[:20]:
                parts = line.split()
                if len(parts) >= 4:
                    output += f"  • {parts[3]} ({parts[5] if len(parts) > 5 else 'N/A'})\n"
            output += "\n"
        
        if scope in ["full", "users"]:
            output += "👤 Usuarios con login:\n"
            result = subprocess.run(
                ["grep", "-v", "nologin", "/etc/passwd"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n')[:5]:
                parts = line.split(':')
                output += f"  • {parts[0]} (uid:{parts[2]})\n"
            output += "\n"
        
        if scope in ["full", "files"]:
            output += "📁 Archivos con permisos 777:\n"
            result = subprocess.run(
                ["find", HOME, "-perm", "777", "-type", "f", "-maxdepth", "3"],
                capture_output=True, text=True, timeout=10
            )
            files = result.stdout.strip().split('\n') if result.stdout.strip() else []
            for f in files[:10]:
                output += f"  ⚠️ {f}\n"
            if not files or files == ['']:
                output += "  ✅ Ninguno encontrado\n"
            output += "\n"
        
        return output
    
    except Exception as e:
        return f"Error en auditoría: {e}"


def tool_secret_detection(path: str = None, extensions: str = ".py,.js,.ts,.env,.json,.yaml,.yml,.cfg,.conf") -> str:
    """Detect potential secrets in code."""
    try:
        if not path:
            path = HOME
        path = os.path.expanduser(path)
        
        # Common secret patterns
        secret_patterns = [
            r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']+["\']',
            r'(?i)(secret|token|api_key|apikey|api-key)\s*[=:]\s*["\'][^"\']+["\']',
            r'(?i)(access_key|secret_key)\s*[=:]\s*["\'][^"\']+["\']',
            r'(?i)(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY)\s*[=:]\s*["\'][^"\']+["\']',
            r'-----BEGIN (RSA |EC )?PRIVATE KEY-----',
            r'(?i)bearer\s+[a-zA-Z0-9_\-\.]+',
        ]
        
        import re
        ext_list = extensions.split(',')
        
        output = "🔐 Detección de Secretos\n\n"
        findings = []
        
        for root, dirs, files in os.walk(path):
            # Skip hidden dirs and common non-code dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', '.git']]
            
            for file in files:
                if any(file.endswith(ext) for ext in ext_list):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        for pattern in secret_patterns:
                            matches = re.findall(pattern, content)
                            for match in matches:
                                if len(match) > 5:  # Skip short matches
                                    findings.append({
                                        "file": filepath,
                                        "pattern": match[:50]
                                    })
                    except Exception:
                        pass
        
        if findings:
            output += f"⚠️ Encontrados {len(findings)} posibles secretos:\n\n"
            for f in findings[:20]:
                output += f"  📄 {f['file']}\n"
                output += f"     {f['pattern']}...\n\n"
        else:
            output += "✅ No se encontraron secretos obvios\n"
        
        return output
    
    except Exception as e:
        return f"Error escaneando: {e}"


# ── Task & Planning Implementations ─────────────────────────
def tool_plan_tasks(objective: str, context: str = None, max_tasks: int = 10) -> str:
    """Generate task plan for an objective."""
    try:
        output = f"📋 Plan de Tareas: {objective}\n\n"
        
        if context:
            output += f"Contexto: {context}\n\n"
        
        # This is a basic template - the LLM will enhance it
        output += "Tareas sugeridas:\n\n"
        output += "1. 🔍 Definir alcance y requisitos\n"
        output += "2. 📊 Analizar recursos disponibles\n"
        output += "3. 🎯 Identificar dependencias\n"
        output += "4. 📝 Crear tareas detalladas\n"
        output += "5. ⏰ Estimar tiempos\n"
        output += "6. 🚀 Ejecutar en orden de prioridad\n"
        output += "7. ✅ Verificar resultados\n"
        output += "8. 📄 Documentar aprendizajes\n"
        
        return output
    
    except Exception as e:
        return f"Error generando plan: {e}"


# ── Enhanced Communication Implementations ──────────────────
def tool_notify_contextual(task: str, result: str, importance: str = "medium", icon: str = None) -> str:
    """Send contextual notification when completing a task."""
    # Determine icon based on importance and task
    if not icon:
        if importance == "critical":
            icon = "dialog-error"
        elif importance == "high":
            icon = "dialog-warning"
        elif "email" in task.lower() or "correo" in task.lower():
            icon = "mail-send"
        elif "backup" in task.lower() or "respaldo" in task.lower():
            icon = "document-save"
        elif "deploy" in task.lower() or "despliegue" in task.lower():
            icon = "system-run"
        elif "error" in result.lower() or "❌" in result:
            icon = "dialog-error"
        elif "✅" in result or "completado" in result.lower():
            icon = "emblem-ok"
        else:
            icon = "dialog-information"

    # Build message
    msg = f"✅ {task}\n{result[:150]}"

    try:
        subprocess.run(
            ["notify-send", "-u", importance if importance in ["low", "normal", "critical"] else "normal",
             "-i", icon, "-a", "AI Lab", "-t", "5000",
             f"🤖 Tarea Completada", msg],
            capture_output=True,
            timeout=3
        )
    except Exception:
        pass

    log_operation("notify_contextual", {"task": task, "importance": importance}, "sent")
    return f"🔔 Notificación enviada: {task}"


# ── Enhanced Search Implementations ─────────────────────────
def _google_search(query: str, max_results: int = 10, language: str = "es", 
                   region: str = "mx", time_filter: str = None, site: str = None) -> list:
    """Perform Google search via scraping."""
    try:
        import requests
        from bs4 import BeautifulSoup

        # Build search URL
        search_query = query
        if site:
            search_query = f"site:{site} {query}"

        params = {
            "q": search_query,
            "hl": language,
            "gl": region,
            "num": max_results
        }

        if time_filter:
            time_map = {"hour": "h1", "day": "d1", "week": "w1", "month": "m1", "year": "y1"}
            params["tbs"] = f"qdr:{time_map.get(time_filter, 'w1')}"

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": f"{language},{language};q=0.9"
        }

        response = requests.get("https://www.google.com/search", params=params, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "lxml")

        results = []

        # Parse search results
        for g in soup.select("div.g"):
            title_el = g.select_one("h3")
            link_el = g.select_one("a")
            snippet_el = g.select_one("div[data-sncf], span.aCOpRe, div.VwiC3b")

            if title_el and link_el:
                title = title_el.get_text(strip=True)
                url = link_el.get("href", "")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                if url.startswith("/url?q="):
                    url = url.split("/url?q=")[1].split("&")[0]

                if url.startswith("http"):
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet[:300]
                    })

            if len(results) >= max_results:
                break

        # Also try to extract AI Mode / featured snippet
        ai_snippet = soup.select_one("div[data-attrid='wa:/description'], div.kb0PBd, div.LGOjhe")
        if ai_snippet:
            ai_text = ai_snippet.get_text(strip=True)
            if ai_text and len(ai_text) > 20:
                results.insert(0, {
                    "title": "🤖 Respuesta AI de Google",
                    "url": "",
                    "snippet": ai_text[:500],
                    "is_ai_mode": True
                })

        return results

    except Exception as e:
        return []


def tool_search_google(query: str, max_results: int = 10, language: str = "es",
                       region: str = "mx", time_filter: str = None, site: str = None) -> str:
    """Search Google with AI Mode support."""
    try:
        results = _google_search(query, max_results, language, region, time_filter, site)

        if not results:
            # Fallback to DuckDuckGo
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    ddg_results = list(ddgs.text(query, max_results=max_results))

                if ddg_results:
                    output = f"🔍 Resultados para '{query}' (DuckDuckGo fallback):\n\n"
                    for i, r in enumerate(ddg_results, 1):
                        output += f"{i}. **{r.get('title', 'N/A')}**\n"
                        output += f"   URL: {r.get('href', 'N/A')}\n"
                        output += f"   {r.get('body', 'N/A')[:200]}\n\n"
                    return output
            except Exception:
                pass

            return f"No se encontraron resultados para: {query}"

        output = f"🔍 Resultados Google para '{query}' ({len(results)} resultados):\n\n"

        for i, r in enumerate(results, 1):
            if r.get("is_ai_mode"):
                output += f"🤖 **AI Mode:**\n{r['snippet']}\n\n"
            else:
                output += f"{i}. **{r['title']}**\n"
                output += f"   URL: {r['url']}\n"
                if r['snippet']:
                    output += f"   {r['snippet']}\n"
                output += "\n"

        log_operation("search_google", {"query": query}, f"{len(results)} results")
        return output

    except Exception as e:
        return f"Error en búsqueda Google: {e}"


def tool_search_sports(query: str, sport: str = "football", live: bool = False) -> str:
    """Search for sports results."""
    try:
        # Build sport-specific query
        sport_sites = {
            "football": ["espndeportes.espn.com", "marca.com", "as.com", ".goal.com", "flashscore.com"],
            "basketball": ["espn.com/nba", "marca.com/baloncesto"],
            "tennis": ["espn.com/tenis", "marca.com/tenis"],
            "f1": ["espn.com/f1", "marca.com/motor"],
            "mma": ["espn.com/mma", "sherdog.com"]
        }

        sites = sport_sites.get(sport, sport_sites["football"])

        # Try Google first
        search_query = query
        if live:
            search_query += " en vivo HOY"

        results = _google_search(search_query, max_results=5, language="es", region="mx")

        if not results:
            # Try specific sports sites
            for site in sites[:2]:
                results = _google_search(f"{query} site:{site}", max_results=3)
                if results:
                    break

        if not results:
            # Fallback to DuckDuckGo news
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.news(f"{query} {sport} resultados", max_results=5))

                if results:
                    output = f"⚽ Resultados deportivos para '{query}':\n\n"
                    for i, r in enumerate(results, 1):
                        output += f"{i}. **{r.get('title', 'N/A')}**\n"
                        output += f"   Fuente: {r.get('source', 'N/A')}\n"
                        output += f"   {r.get('url', 'N/A')}\n\n"
                    return output
            except Exception:
                pass

            return f"No se encontraron resultados deportivos para: {query}"

        output = f"⚽ Resultados deportivos para '{query}':\n\n"

        for i, r in enumerate(results[:5], 1):
            output += f"{i}. **{r['title']}**\n"
            output += f"   {r['url']}\n"
            if r['snippet']:
                output += f"   {r['snippet'][:200]}\n"
            output += "\n"

        log_operation("search_sports", {"query": query, "sport": sport}, f"{len(results)} results")
        return output

    except Exception as e:
        return f"Error buscando deportes: {e}"


def tool_fetch_article(url: str, max_chars: int = 5000, extract_links: bool = False) -> str:
    """Fetch and extract article content using BeautifulSoup."""
    try:
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Remove unwanted elements
        for tag in soup.select("script, style, nav, footer, header, aside, .ad, .advertisement, .sidebar"):
            tag.decompose()

        # Try to find main content
        article = None
        selectors = [
            "article", "main", "[role='main']",
            ".article-content", ".post-content", ".entry-content",
            ".story-body", ".article-body", ".content-body"
        ]

        for selector in selectors:
            article = soup.select_one(selector)
            if article:
                break

        if not article:
            article = soup.body or soup

        # Extract text
        text = article.get_text(separator="\n", strip=True)

        # Clean up whitespace
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        # Extract title
        title = ""
        title_tag = soup.select_one("h1") or soup.select_one("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Build output
        output = f"📄 **{title}**\n"
        output += f"🌐 {url}\n\n"
        output += text[:max_chars]

        if len(text) > max_chars:
            output += f"\n\n... [{len(text) - max_chars} caracteres más]"

        # Extract links if requested
        if extract_links:
            links = []
            for a in article.select("a[href]"):
                href = a.get("href", "")
                link_text = a.get_text(strip=True)
                if href.startswith("http") and link_text and len(link_text) > 5:
                    links.append(f"  - [{link_text}]({href})")

            if links:
                output += f"\n\n🔗 Enlaces encontrados ({len(links)}):\n"
                output += "\n".join(links[:20])

        log_operation("fetch_article", {"url": url}, f"{len(text)} chars")
        return output

    except Exception as e:
        return f"Error obteniendo artículo: {e}"


def tool_search_with_content(query: str, max_chars: int = 3000, site: str = None) -> str:
    """Search Google and fetch content from first result."""
    try:
        # Search
        results = _google_search(query, max_results=3, site=site)

        if not results:
            return f"No se encontraron resultados para: {query}"

        output = f"🔍 Búsqueda: '{query}'\n\n"

        # Try to fetch first result with content
        first_result = None
        for r in results:
            if r.get("url") and r["url"].startswith("http"):
                first_result = r
                break

        if first_result:
            output += f"📄 **{first_result['title']}**\n"
            output += f"🌐 {first_result['url']}\n\n"

            # Fetch content
            try:
                import requests
                from bs4 import BeautifulSoup

                headers = {
                    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                }

                response = requests.get(first_result["url"], headers=headers, timeout=10)
                soup = BeautifulSoup(response.text, "lxml")

                # Remove unwanted
                for tag in soup.select("script, style, nav, footer, header, aside"):
                    tag.decompose()

                # Find content
                article = soup.select_one("article, main, [role='main']") or soup.body
                if article:
                    text = article.get_text(separator="\n", strip=True)
                    import re
                    text = re.sub(r'\n{3,}', '\n\n', text)
                    output += text[:max_chars]
                else:
                    output += first_result.get("snippet", "Sin contenido disponible")
            except Exception:
                output += first_result.get("snippet", "Error obteniendo contenido")
        else:
            # Just show snippets
            for i, r in enumerate(results, 1):
                output += f"{i}. **{r['title']}**\n"
                output += f"   {r.get('snippet', 'N/A')[:200]}\n\n"

        log_operation("search_with_content", {"query": query}, "OK")
        return output

    except Exception as e:
        return f"Error: {e}"


# ── OSINT Implementations ───────────────────────────────────
def tool_osint_username(username: str, sites: str = None, max_results: int = 50) -> str:
    """Search username across 3000+ platforms using maigret/sherlock."""
    try:
        import subprocess
        import json
        import os

        # Use maigret as primary (3302 sites)
        venv_python = "/tmp/search-env/bin/python"

        # Build maigret command
        cmd = [
            venv_python, "-m", "maigret",
            username,
            "--json",
            "--no-errors",
            "-t", str(min(max_results, 100))  # limit timeout
        ]

        # Add specific sites if provided
        if sites:
            site_list = [s.strip() for s in sites.split(",")]
            for site in site_list:
                cmd.extend(["-s", site])

        # Run maigret with timeout
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                env={**os.environ, "PATH": f"/tmp/search-env/bin:{os.environ.get('PATH', '')}"}
            )

            # Parse JSON output
            output = result.stdout
            if output:
                try:
                    data = json.loads(output)
                except json.JSONDecodeError:
                    # Try to extract JSON from output
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', output)
                    if json_match:
                        data = json.loads(json_match.group())
                    else:
                        data = {}
            else:
                data = {}

        except subprocess.TimeoutExpired:
            data = {}
            output = "Maigret timeout - using fallback"
        except FileNotFoundError:
            data = {}
            output = "Maigret not found"

        # Format output
        if data:
            accounts = []
            for site_name, site_data in data.items():
                if isinstance(site_data, dict):
                    status = site_data.get("status", "unknown")
                    url = site_data.get("url_user", "")
                    if status in ["Claimed", "Found", "exists"]:
                        accounts.append({
                            "site": site_name,
                            "url": url,
                            "status": status
                        })

            if accounts:
                output = f"🔍 **Username: {username}**\n"
                output += f"📊 Encontrado en {len(accounts)} plataformas:\n\n"

                for acc in accounts[:max_results]:
                    output += f"• {acc['site']}: {acc['url']}\n"

                log_operation("osint_username", {"username": username}, f"{len(accounts)} accounts")
                return output

        # Fallback: try sherlock
        try:
            cmd = [
                venv_python, "-m", "sherlock",
                username,
                "--json",
                "--print-found"
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                env={**os.environ, "PATH": f"/tmp/search-env/bin:{os.environ.get('PATH', '')}"}
            )

            if result.stdout:
                # Parse sherlock output
                accounts = []
                for line in result.stdout.split('\n'):
                    if 'http' in line.lower() and username.lower() in line.lower():
                        accounts.append(line.strip())

                if accounts:
                    output = f"🔍 **Username: {username}**\n"
                    output += f"📊 Sherlock encontró {len(accounts)} cuentas:\n\n"
                    for acc in accounts[:max_results]:
                        output += f"• {acc}\n"
                    log_operation("osint_username", {"username": username}, f"{len(accounts)} (sherlock)")
                    return output
        except Exception:
            pass

        return f"No se encontró el username '{username}' en las plataformas buscadas"

    except Exception as e:
        return f"Error en OSINT username: {e}"


def tool_osint_email(email: str, max_results: int = 30) -> str:
    """Find social accounts from email using holehe."""
    try:
        import subprocess
        import json
        import os

        venv_python = "/tmp/search-env/bin/python"

        # Use holehe for email investigation
        cmd = [
            venv_python, "-m", "holehe",
            email,
            "--json"
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                env={**os.environ, "PATH": f"/tmp/search-env/bin:{os.environ.get('PATH', '')}"}
            )

            # Parse output
            output = result.stdout
            accounts = []

            if output:
                try:
                    data = json.loads(output)
                    if isinstance(data, list):
                        accounts = data
                    elif isinstance(data, dict):
                        accounts = data.get("accounts", [])
                except json.JSONDecodeError:
                    # Parse line by line
                    for line in output.split('\n'):
                        if 'http' in line.lower() or 'true' in line.lower():
                            accounts.append({"site": line.strip(), "exists": True})

        except subprocess.TimeoutExpired:
            accounts = []
        except FileNotFoundError:
            accounts = []

        # Fallback: check common platforms with requests
        if not accounts:
            try:
                import requests
                from bs4 import BeautifulSoup

                common_platforms = {
                    "GitHub": f"https://github.com/{email.split('@')[0]}",
                    "Twitter": f"https://twitter.com/{email.split('@')[0]}",
                    "Instagram": f"https://www.instagram.com/{email.split('@')[0]}/",
                }

                for platform, url in common_platforms.items():
                    try:
                        resp = requests.get(url, timeout=5, allow_redirects=False,
                                          headers={"User-Agent": "Mozilla/5.0"})
                        if resp.status_code == 200:
                            accounts.append({"site": platform, "url": url, "exists": True})
                    except Exception:
                        pass
            except Exception:
                pass

        # Format output
        if accounts:
            output = f"📧 **Email: {email}**\n"
            output += f"📊 Cuentas encontradas: {len(accounts)}\n\n"

            for acc in accounts[:max_results]:
                if isinstance(acc, dict):
                    site = acc.get("site", acc.get("name", "Unknown"))
                    url = acc.get("url", "")
                    if url:
                        output += f"• {site}: {url}\n"
                    else:
                        output += f"• {site}\n"
                else:
                    output += f"• {acc}\n"

            log_operation("osint_email", {"email": email}, f"{len(accounts)} accounts")
            return output

        return f"No se encontraron cuentas para el email: {email}"

    except Exception as e:
        return f"Error en OSINT email: {e}"


def tool_osint_domain(domain: str) -> str:
    """Gather intelligence about a domain (DNS, WHOIS, subdomains)."""
    try:
        import dns.resolver
        import whois
        import tldextract
        import requests
        from bs4 import BeautifulSoup

        output = f"🌐 **Dominio: {domain}**\n\n"

        # Extract domain parts
        ext = tldextract.extract(domain)
        output += f"📌 Registrado: {ext.registered_domain}\n"
        output += f"📌 Subdominio: {ext.subdomain or '(ninguno)'}\n"
        output += f"📌 TLD: {ext.suffix}\n\n"

        # DNS Records
        output += "### 📡 Registros DNS\n"
        record_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]

        for rtype in record_types:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                records = [str(r) for r in answers]
                if records:
                    output += f"\n**{rtype}:**\n"
                    for r in records[:5]:
                        output += f"  • {r[:100]}\n"
            except Exception:
                pass

        # WHOIS
        output += "\n### 📋 WHOIS\n"
        try:
            w = whois.whois(domain)
            if w:
                if w.registrar:
                    output += f"• Registrar: {w.registrar}\n"
                if w.creation_date:
                    creation = w.creation_date
                    if isinstance(creation, list):
                        creation = creation[0]
                    output += f"• Creado: {creation}\n"
                if w.expiration_date:
                    exp = w.expiration_date
                    if isinstance(exp, list):
                        exp = exp[0]
                    output += f"• Expira: {exp}\n"
                if w.name_servers:
                    ns = w.name_servers if isinstance(w.name_servers, list) else [w.name_servers]
                    output += f"• Name Servers: {', '.join(ns[:3])}\n"
                if w.org:
                    output += f"• Organización: {w.org}\n"
                if w.country:
                    output += f"• País: {w.country}\n"
        except Exception as e:
            output += f"• Error WHOIS: {e}\n"

        # Check for common subdomains
        output += "\n### 🔍 Subdominios Comunes\n"
        common_subdomains = ["www", "mail", "ftp", "smtp", "pop", "webmail", "admin", "api", "dev", "staging"]
        found_subdomains = []

        for sub in common_subdomains:
            try:
                subdomain = f"{sub}.{domain}"
                dns.resolver.resolve(subdomain, "A")
                found_subdomains.append(subdomain)
                output += f"• ✅ {subdomain}\n"
            except Exception:
                pass

        if not found_subdomains:
            output += "• No se encontraron subdominios comunes\n"

        # Check HTTP/HTTPS
        output += "\n### 🌐 Conectividad\n"
        for protocol in ["https", "http"]:
            try:
                resp = requests.get(f"{protocol}://{domain}", timeout=5,
                                   allow_redirects=True,
                                   headers={"User-Agent": "Mozilla/5.0"})
                output += f"• {protocol.upper()}: {resp.status_code} ({resp.url[:50]})\n"
            except Exception as e:
                output += f"• {protocol.upper()}: No disponible\n"

        log_operation("osint_domain", {"domain": domain}, "OK")
        return output

    except Exception as e:
        return f"Error en OSINT dominio: {e}"


def tool_osint_ip(ip_address: str) -> str:
    """Gather intelligence about an IP address."""
    try:
        import requests
        from ipwhois import IPWhois

        output = f"🌐 **IP: {ip_address}**\n\n"

        # IP WHOIS
        output += "### 📋 WHOIS IP\n"
        try:
            w = IPWhois(ip_address)
            result = w.lookup_rdap()

            if result:
                if result.get("asn"):
                    output += f"• ASN: {result['asn']}\n"
                if result.get("asn_description"):
                    output += f"• Descripción ASN: {result['asn_description']}\n"
                if result.get("asn_country_code"):
                    output += f"• País ASN: {result['asn_country_code']}\n"
                if result.get("network", {}).get("name"):
                    output += f"• Red: {result['network']['name']}\n"
                if result.get("objects"):
                    for obj_key, obj_data in result["objects"].items():
                        if isinstance(obj_data, dict):
                            contact = obj_data.get("contact", {})
                            if contact.get("name"):
                                output += f"• Propietario: {contact['name']}\n"
                                break
        except Exception as e:
            output += f"• Error WHOIS: {e}\n"

        # Geolocation (free API)
        output += "\n### 📍 Geolocalización\n"
        try:
            resp = requests.get(f"http://ip-api.com/json/{ip_address}", timeout=5)
            if resp.status_code == 200:
                geo = resp.json()
                if geo.get("status") == "success":
                    output += f"• País: {geo.get('country', 'N/A')}\n"
                    output += f"• Región: {geo.get('regionName', 'N/A')}\n"
                    output += f"• Ciudad: {geo.get('city', 'N/A')}\n"
                    output += f"• ISP: {geo.get('isp', 'N/A')}\n"
                    output += f"• Organización: {geo.get('org', 'N/A')}\n"
                    output += f"• ASN: {geo.get('as', 'N/A')}\n"
        except Exception:
            output += "• Geolocalización no disponible\n"

        # Reverse DNS
        output += "\n### 🔍 Reverse DNS\n"
        try:
            import socket
            hostname = socket.gethostbyaddr(ip_address)
            output += f"• Hostname: {hostname[0]}\n"
            if hostname[1]:
                output += f"• Aliases: {', '.join(hostname[1])}\n"
        except Exception:
            output += "• Sin reverse DNS\n"

        # Check common ports
        output += "\n### 🔌 Puertos Comunes\n"
        common_ports = [22, 80, 443, 8080, 8443]
        open_ports = []

        for port in common_ports:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((ip_address, port))
                if result == 0:
                    open_ports.append(port)
                    output += f"• ✅ Puerto {port}: Abierto\n"
                sock.close()
            except Exception:
                pass

        if not open_ports:
            output += "• No se detectaron puertos abiertos (limitado por timeout)\n"

        log_operation("osint_ip", {"ip": ip_address}, "OK")
        return output

    except Exception as e:
        return f"Error en OSINT IP: {e}"


def tool_osint_person(name: str, email: str = None, location: str = None) -> str:
    """Search for a person across platforms by name."""
    try:
        output = f"👤 **Búsqueda OSINT: {name}**\n\n"

        # Generate username variations
        name_parts = name.lower().split()
        username_variations = set()

        if len(name_parts) >= 2:
            first = name_parts[0]
            last = name_parts[-1]

            # Common username patterns
            username_variations.add(f"{first}{last}")
            username_variations.add(f"{first}.{last}")
            username_variations.add(f"{first}_{last}")
            username_variations.add(f"{first[0]}{last}")
            username_variations.add(f"{first}{last[0]}")
            username_variations.add(f"{last}{first}")
            username_variations.add(f"{last}.{first}")

            # With numbers
            for i in range(10):
                username_variations.add(f"{first}{last}{i}")
                username_variations.add(f"{first}.{last}{i}")

        # Add email username if provided
        if email:
            email_user = email.split("@")[0]
            username_variations.add(email_user)

        output += f"🔍 Buscando variaciones de username: {len(username_variations)}\n\n"

        # Search each variation (limit to avoid timeout)
        found_accounts = []
        search_limit = min(len(username_variations), 5)

        for i, username in enumerate(list(username_variations)[:search_limit]):
            try:
                # Use simple HTTP check for each platform
                platforms = {
                    "GitHub": f"https://github.com/{username}",
                    "Twitter": f"https://twitter.com/{username}",
                    "Instagram": f"https://www.instagram.com/{username}/",
                    "Reddit": f"https://www.reddit.com/user/{username}",
                    "LinkedIn": f"https://www.linkedin.com/in/{username}",
                }

                for platform, url in platforms.items():
                    try:
                        import requests
                        resp = requests.get(url, timeout=5, allow_redirects=False,
                                          headers={"User-Agent": "Mozilla/5.0"})
                        if resp.status_code == 200:
                            found_accounts.append({
                                "platform": platform,
                                "url": url,
                                "username": username
                            })
                    except Exception:
                        pass

            except Exception:
                pass

        if found_accounts:
            output += f"📊 **Cuentas encontradas:** {len(found_accounts)}\n\n"
            for acc in found_accounts:
                output += f"• {acc['platform']}: [{acc['username']}]({acc['url']})\n"
        else:
            output += "No se encontraron cuentas con las variaciones buscadas\n"
            output += "💡 Prueba con la herramienta `osint_username` para una búsqueda más profunda\n"

        # Search location if provided
        if location:
            output += f"\n📍 **Ubicación:** {location}\n"
            output += "ℹ️ La información de ubicación es pública y puede requerir verificación\n"

        log_operation("osint_person", {"name": name, "email": email}, f"{len(found_accounts)} accounts")
        return output

    except Exception as e:
        return f"Error en OSINT persona: {e}"


def handle_request(request: dict) -> dict:
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "system-mcp-server",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            handlers = {
                "list_directory": lambda: tool_list_directory(
                    arguments.get("path"),
                    arguments.get("show_hidden", False)
                ),
                "file_info": lambda: tool_file_info(arguments["path"]),
                "search_files": lambda: tool_search_files(
                    arguments["pattern"],
                    arguments.get("path")
                ),
                "read_file": lambda: tool_read_file(
                    arguments["path"],
                    arguments.get("max_lines", 200)
                ),
                "write_file": lambda: tool_write_file(
                    arguments["path"],
                    arguments["content"],
                    arguments.get("append", False)
                ),
                "run_command": lambda: tool_run_command(
                    arguments["command"],
                    arguments.get("confirm", False)
                ),
                "get_system_info": lambda: tool_get_system_info(),
                "get_gpu_status": lambda: tool_get_gpu_status(),
                "web_search": lambda: tool_web_search(
                    arguments["query"],
                    arguments.get("max_results", 5),
                    arguments.get("region", "wt-wt")
                ),
                "open_url": lambda: tool_open_url(arguments["url"]),
                "run_python_script": lambda: tool_run_python_script(
                    arguments["script"],
                    arguments.get("timeout", 30)
                ),
                "media_control": lambda: tool_media_control(arguments["action"]),
                "send_notification": lambda: tool_send_notification(
                    arguments["title"],
                    arguments["message"],
                    arguments.get("urgency", "normal"),
                    arguments.get("icon"),
                    arguments.get("timeout", 5000),
                    arguments.get("category"),
                    arguments.get("transient", False)
                ),
                "spotify_search": lambda: tool_spotify_search(
                    arguments["query"],
                    arguments.get("limit", 5)
                ),
                "spotify_now": lambda: tool_spotify_now(),
                "spotify_play": lambda: tool_spotify_play(),
                "spotify_pause": lambda: tool_spotify_pause(),
                "spotify_next": lambda: tool_spotify_next(),
                "spotify_previous": lambda: tool_spotify_previous(),
                "spotify_volume": lambda: tool_spotify_volume(arguments["level"]),
                "spotify_playlists": lambda: tool_spotify_playlists(),
                "spotify_launch": lambda: tool_spotify_launch(),
                "spotify_play_track": lambda: tool_spotify_play_track(arguments["query"]),
                "spotify_play_artist": lambda: tool_spotify_play_artist(arguments["artist"]),
                "spotify_play_playlist": lambda: tool_spotify_play_playlist(arguments["name"]),
                "delegate_to_subagent": lambda: tool_delegate_to_subagent(arguments["query"]),
                "screenshot": lambda: tool_screenshot(
                    arguments.get("filename"),
                    arguments.get("delay", 0)
                ),
                "clipboard": lambda: tool_clipboard(
                    arguments["action"],
                    arguments.get("text")
                ),
                "brightness": lambda: tool_brightness(
                    arguments["action"],
                    arguments.get("level")
                ),
                "weather": lambda: tool_weather(arguments.get("city")),
                "timer": lambda: tool_timer(
                    arguments["minutes"],
                    arguments["message"]
                ),
                "notes": lambda: tool_notes(
                    arguments["action"],
                    arguments.get("title"),
                    arguments.get("content"),
                    arguments.get("category", "General")
                ),
                "memory_save": lambda: tool_memory_save(
                    arguments["category"],
                    arguments["content"],
                    arguments.get("title"),
                    arguments.get("tags", "")
                ),
                "memory_search": lambda: tool_memory_search(
                    arguments["query"],
                    arguments.get("category"),
                    arguments.get("limit", 10)
                ),
                "memory_context": lambda: tool_memory_context(
                    arguments.get("category"),
                    arguments.get("limit", 5)
                ),
                "memory_list": lambda: tool_memory_list(
                    arguments.get("limit", 20)
                ),
                "memory_delete": lambda: tool_memory_delete(arguments["id"]),
                "system_shutdown": lambda: tool_system_shutdown(
                    arguments["action"],
                    arguments.get("delay", 0),
                    arguments.get("confirm", False)
                ),
                "file_compress": lambda: tool_file_compress(
                    arguments["source"],
                    arguments.get("format", "tar.gz")
                ),
                "file_extract": lambda: tool_file_extract(
                    arguments["source"],
                    arguments.get("destination")
                ),
                "file_permissions": lambda: tool_file_permissions(
                    arguments["path"],
                    arguments["mode"]
                ),
                "network_ping": lambda: tool_network_ping(
                    arguments["host"],
                    arguments.get("count", 4)
                ),
                "network_ports": lambda: tool_network_ports(
                    arguments.get("filter", "LISTEN")
                ),
                "network_speed": lambda: tool_network_speed(),
                "network_info": lambda: tool_network_info(),
                "process_list": lambda: tool_process_list(
                    arguments.get("sort_by", "cpu"),
                    arguments.get("limit", 20)
                ),
                "process_kill": lambda: tool_process_kill(
                    arguments.get("pid"),
                    arguments.get("name"),
                    arguments.get("signal", "TERM"),
                    arguments.get("confirm", False)
                ),
                "process_search": lambda: tool_process_search(arguments["query"]),
                "cron_list": lambda: tool_cron_list(),
                "cron_add": lambda: tool_cron_add(
                    arguments["schedule"],
                    arguments["command"],
                    arguments.get("description")
                ),
                "cron_delete": lambda: tool_cron_delete(arguments["line_number"]),
                "audio_list_devices": lambda: tool_audio_list_devices(),
                "audio_set_source": lambda: tool_audio_set_source(arguments["sink"]),
                "audio_set_source_input": lambda: tool_audio_set_source_input(arguments["source"]),
                "monitor_realtime": lambda: tool_monitor_realtime(
                    arguments.get("metrics", "all")
                ),
                "monitor_top_processes": lambda: tool_monitor_top_processes(
                    arguments.get("by", "cpu"),
                    arguments.get("limit", 10)
                ),
                "disk_usage": lambda: tool_disk_usage(),
                "disk_io": lambda: tool_disk_io(),
                "gh_repos_list": lambda: tool_gh_repos_list(
                    arguments.get("limit", 20),
                    arguments.get("visibility", "all")
                ),
                "gh_repo_info": lambda: tool_gh_repo_info(arguments["repo"]),
                "gh_repo_create": lambda: tool_gh_repo_create(
                    arguments["name"],
                    arguments.get("description"),
                    arguments.get("private", False),
                    arguments.get("auto_init", True)
                ),
                "gh_issues_list": lambda: tool_gh_issues_list(
                    arguments["repo"],
                    arguments.get("state", "open"),
                    arguments.get("limit", 20)
                ),
                "gh_issue_create": lambda: tool_gh_issue_create(
                    arguments["repo"],
                    arguments["title"],
                    arguments.get("body"),
                    arguments.get("labels")
                ),
                "gh_pr_list": lambda: tool_gh_pr_list(
                    arguments["repo"],
                    arguments.get("state", "open"),
                    arguments.get("limit", 20)
                ),
                "gh_pr_create": lambda: tool_gh_pr_create(
                    arguments["repo"],
                    arguments["title"],
                    arguments.get("body"),
                    arguments.get("head"),
                    arguments.get("base", "main")
                ),
                "gh_pr_merge": lambda: tool_gh_pr_merge(
                    arguments["repo"],
                    arguments["pr_number"]
                ),
                "gh_actions_list": lambda: tool_gh_actions_list(arguments["repo"]),
                "gh_actions_runs": lambda: tool_gh_actions_runs(
                    arguments["repo"],
                    arguments.get("limit", 10)
                ),
                "gh_release_list": lambda: tool_gh_release_list(
                    arguments["repo"],
                    arguments.get("limit", 10)
                ),
                "gh_gist_list": lambda: tool_gh_gist_list(
                    arguments.get("limit", 20)
                ),
                "gh_gist_create": lambda: tool_gh_gist_create(
                    arguments["filename"],
                    arguments["content"],
                    arguments.get("description"),
                    arguments.get("public", False)
                ),
                "gh_search_repos": lambda: tool_gh_search_repos(
                    arguments["query"],
                    arguments.get("limit", 10),
                    arguments.get("language"),
                    arguments.get("sort", "stars")
                ),
                "gh_search_code": lambda: tool_gh_search_code(
                    arguments["query"],
                    arguments.get("repo"),
                    arguments.get("language"),
                    arguments.get("limit", 10)
                ),
                "git_status": lambda: tool_git_status(arguments.get("path")),
                "git_log": lambda: tool_git_log(
                    arguments.get("path"),
                    arguments.get("limit", 10),
                    arguments.get("branch")
                ),
                "git_diff": lambda: tool_git_diff(
                    arguments.get("path"),
                    arguments.get("file"),
                    arguments.get("staged", False)
                ),
                "git_branches": lambda: tool_git_branches(arguments.get("path")),
                "git_commit": lambda: tool_git_commit(
                    arguments.get("path"),
                    arguments["message"],
                    arguments.get("add_all", False)
                ),
                "git_push": lambda: tool_git_push(
                    arguments.get("path"),
                    arguments.get("branch")
                ),
                "git_pull": lambda: tool_git_pull(arguments.get("path")),
                "git_clone": lambda: tool_git_clone(
                    arguments["url"],
                    arguments.get("destination")
                ),
                "code_analyze": lambda: tool_code_analyze(arguments["path"]),
                "code_count_lines": lambda: tool_code_count_lines(
                    arguments.get("path"),
                    arguments.get("extension")
                ),
                "code_search_pattern": lambda: tool_code_search_pattern(
                    arguments["pattern"],
                    arguments.get("path"),
                    arguments.get("extension")
                ),
                "project_dependencies": lambda: tool_project_dependencies(
                    arguments.get("path")
                ),
                "project_structure": lambda: tool_project_structure(
                    arguments.get("path"),
                    arguments.get("depth", 3)
                ),
                "docker_ps": lambda: tool_docker_ps(arguments.get("all", False)),
                "docker_logs": lambda: tool_docker_logs(
                    arguments["container"],
                    arguments.get("lines", 50)
                ),
                "docker_images": lambda: tool_docker_images(),
                "chat_export": lambda: tool_chat_export(
                    arguments["messages"],
                    arguments.get("title")
                ),
                "chat_list_shared": lambda: tool_chat_list_shared(),
                "chat_get_shared": lambda: tool_chat_get_shared(arguments["chat_id"]),
                # Email tools
                "email_send": lambda: tool_email_send(
                    arguments["to"],
                    arguments["subject"],
                    arguments["body"],
                    arguments.get("cc"),
                    arguments.get("bcc"),
                    arguments.get("html", False),
                    arguments.get("attachments")
                ),
                "email_configure": lambda: tool_email_configure(
                    arguments["smtp_host"],
                    arguments["username"],
                    arguments["password"],
                    arguments["from_email"],
                    arguments.get("smtp_port", 587),
                    arguments.get("from_name"),
                    arguments.get("tls", True)
                ),
                "email_test": lambda: tool_email_test(arguments.get("to")),
                # SSH tools
                "ssh_connect": lambda: tool_ssh_connect(
                    arguments["host"],
                    arguments["command"],
                    arguments.get("user"),
                    arguments.get("port", 22),
                    arguments.get("timeout", 30)
                ),
                "ssh_copy": lambda: tool_ssh_copy(
                    arguments["host"],
                    arguments["local_path"],
                    arguments["remote_path"],
                    arguments.get("user"),
                    arguments.get("port", 22)
                ),
                "ssh_fetch": lambda: tool_ssh_fetch(
                    arguments["host"],
                    arguments["remote_path"],
                    arguments["local_path"],
                    arguments.get("user"),
                    arguments.get("port", 22)
                ),
                "ssh_sync": lambda: tool_ssh_sync(
                    arguments["host"],
                    arguments["local_path"],
                    arguments["remote_path"],
                    arguments.get("user"),
                    arguments.get("port", 22),
                    arguments.get("delete", False),
                    arguments.get("exclude")
                ),
                "ssh_tunnel": lambda: tool_ssh_tunnel(
                    arguments["host"],
                    arguments["local_port"],
                    arguments["remote_port"],
                    arguments.get("user"),
                    arguments.get("ssh_port", 22),
                    arguments.get("background", True)
                ),
                "ssh_list_hosts": lambda: tool_ssh_list_hosts(),
                "ssh_add_host": lambda: tool_ssh_add_host(
                    arguments["hostname"],
                    arguments["host"],
                    arguments.get("user", "darkseid"),
                    arguments.get("port", 22),
                    arguments.get("identity_file")
                ),
                "ssh_status": lambda: tool_ssh_status(arguments["host"]),
                # Communication tools
                "email_discover_settings": lambda: tool_email_discover_settings(
                    arguments["email"]
                ),
                "email_setup_wizard": lambda: tool_email_setup_wizard(
                    arguments["email"],
                    arguments["password"],
                    arguments.get("display_name")
                ),
                "format_whatsapp": lambda: tool_format_whatsapp(
                    arguments["elements"],
                    arguments.get("copy_to_clipboard", True)
                ),
                "whatsapp_link": lambda: tool_whatsapp_link(
                    arguments["phone"],
                    arguments["message"],
                    arguments.get("copy_to_clipboard", True)
                ),
                "format_email": lambda: tool_format_email(
                    arguments.get("to"),
                    arguments.get("subject"),
                    arguments.get("greeting"),
                    arguments["body"],
                    arguments.get("bullets"),
                    arguments.get("signature"),
                    arguments.get("format", "both"),
                    arguments.get("copy_to_clipboard", False)
                ),
                # Web & Internet tools
                "browse_web": lambda: tool_browse_web(
                    arguments["url"],
                    arguments.get("format", "text"),
                    arguments.get("timeout", 30)
                ),
                "http_request": lambda: tool_http_request(
                    arguments["url"],
                    arguments.get("method", "GET"),
                    arguments.get("headers"),
                    arguments.get("body"),
                    arguments.get("timeout", 30)
                ),
                "search_news": lambda: tool_search_news(
                    arguments["query"],
                    arguments.get("region", "wt-wt"),
                    arguments.get("time", "w"),
                    arguments.get("max_results", 10)
                ),
                "search_docs": lambda: tool_search_docs(
                    arguments["query"],
                    arguments.get("language"),
                    arguments.get("max_results", 5)
                ),
                "dns_lookup": lambda: tool_dns_lookup(
                    arguments["domain"],
                    arguments.get("record_type", "ALL")
                ),
                "ssl_check": lambda: tool_ssl_check(arguments["domain"]),
                "whois_lookup": lambda: tool_whois_lookup(arguments["domain"]),
                # Database tools
                "sql_query": lambda: tool_sql_query(
                    arguments["query"],
                    arguments.get("database"),
                    arguments.get("params")
                ),
                "backup_database": lambda: tool_backup_database(
                    arguments["database"],
                    arguments.get("backup_path")
                ),
                # Data processing tools
                "csv_to_json": lambda: tool_csv_to_json(
                    arguments["input_file"],
                    arguments.get("output_file")
                ),
                "json_to_csv": lambda: tool_json_to_csv(
                    arguments["input_file"],
                    arguments.get("output_file")
                ),
                "convert_file": lambda: tool_convert_file(
                    arguments["input_file"],
                    arguments["output_format"],
                    arguments.get("output_file")
                ),
                "extract_pdf": lambda: tool_extract_pdf(
                    arguments["pdf_path"],
                    arguments.get("pages", "all")
                ),
                "generate_csv": lambda: tool_generate_csv(
                    arguments["data"],
                    arguments["output_file"],
                    arguments.get("delimiter", ",")
                ),
                "data_analysis": lambda: tool_data_analysis(
                    arguments["file_path"],
                    arguments.get("column")
                ),
                # Log & System tools
                "log_analysis": lambda: tool_log_analysis(
                    arguments["log_file"],
                    arguments.get("lines", 100),
                    arguments.get("filter")
                ),
                "generate_report": lambda: tool_generate_report(
                    arguments["title"],
                    arguments["sections"],
                    arguments.get("output_file")
                ),
                # Security tools
                "security_audit": lambda: tool_security_audit(
                    arguments.get("scope", "full")
                ),
                "secret_detection": lambda: tool_secret_detection(
                    arguments.get("path"),
                    arguments.get("extensions", ".py,.js,.ts,.env,.json,.yaml,.yml,.cfg,.conf")
                ),
                # Task tools
                "plan_tasks": lambda: tool_plan_tasks(
                    arguments["objective"],
                    arguments.get("context"),
                    arguments.get("max_tasks", 10)
                ),
                # Enhanced Communication tools
                "notify_contextual": lambda: tool_notify_contextual(
                    arguments["task"],
                    arguments["result"],
                    arguments.get("importance", "medium"),
                    arguments.get("icon")
                ),
                # Enhanced Search tools
                "search_google": lambda: tool_search_google(
                    arguments["query"],
                    arguments.get("max_results", 10),
                    arguments.get("language", "es"),
                    arguments.get("region", "mx"),
                    arguments.get("time_filter"),
                    arguments.get("site")
                ),
                "search_sports": lambda: tool_search_sports(
                    arguments["query"],
                    arguments.get("sport", "football"),
                    arguments.get("live", False)
                ),
                "fetch_article": lambda: tool_fetch_article(
                    arguments["url"],
                    arguments.get("max_chars", 5000),
                    arguments.get("extract_links", False)
                ),
                "search_with_content": lambda: tool_search_with_content(
                    arguments["query"],
                    arguments.get("max_chars", 3000),
                    arguments.get("site")
                ),
                # OSINT tools
                "osint_username": lambda: tool_osint_username(
                    arguments["username"],
                    arguments.get("sites"),
                    arguments.get("max_results", 50)
                ),
                "osint_email": lambda: tool_osint_email(
                    arguments["email"],
                    arguments.get("max_results", 30)
                ),
                "osint_domain": lambda: tool_osint_domain(
                    arguments["domain"]
                ),
                "osint_ip": lambda: tool_osint_ip(
                    arguments["ip_address"]
                ),
                "osint_person": lambda: tool_osint_person(
                    arguments["name"],
                    arguments.get("email"),
                    arguments.get("location")
                )
            }

            if tool_name not in handlers:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                }

            result = handlers[tool_name]()

            # Auto-notification hook
            try:
                if _should_notify(tool_name, result, _notify_config):
                    _send_auto_notification(tool_name, arguments, result)
            except Exception:
                pass

            log_operation(tool_name, arguments, result[:100])

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result}]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "isError": True
                }
            }

    elif method == "notifications/initialized":
        return None

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }


# ── Main loop: stdin → stdout ─────────────────────────────
if __name__ == "__main__":
    # Load notification config at startup
    _notify_config = _load_notify_config()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
