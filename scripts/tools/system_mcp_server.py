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
from datetime import datetime

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

BLOCKED_COMMANDS = [
    "rm -rf /", "rm -rf /*", "dd if=", "mkfs", "chmod 777",
    "> /dev/sd", ":(){ :|:& };:", "mv / ", "rm -r /home",
    "rm -rf ~", "rm -rf /root"
]

DESTRUCTIVE_PATTERNS = ["rm ", "mv ", "chmod ", "chown ", "kill ", "pkill ", "> ", ">> "]

LOG_FILE = os.path.join(HOME, ".config/system-tools.log")


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
        "description": "Envía una notificación de escritorio.",
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


def tool_send_notification(title: str, message: str) -> str:
    try:
        subprocess.run(
            ["notify-send", title, message],
            capture_output=True, timeout=5
        )
        log_operation("send_notification", {"title": title}, "sent")
        return f"🔔 Notificación enviada: {title}"
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


# ── MCP JSON-RPC Handler ─────────────────────────────────
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
                    arguments["message"]
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
                "disk_io": lambda: tool_disk_io()
            }

            if tool_name not in handlers:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                }

            result = handlers[tool_name]()
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
