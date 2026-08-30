# GPU Tools & Gemma 4 AI Server

Suite completa para gestión de GPU NVIDIA, servidor de IA local con Gemma 4, sistema de memoria persistente y 94 tools MCP.

Consulta la sección "Quickstart" en el `README.md` para pasos rápidos de instalación y puesta en marcha.

## Hardware

| Componente | Detalle |
|---|---|
| GPU | NVIDIA RTX 5060 Laptop (8GB VRAM) |
| RAM | 16GB |
| Driver | NVIDIA 580.173.02 (open kernel module) |
| CUDA | 12.0 |
| llama.cpp | v0.3.0-dev (b10688) |
| SO | Pop!_OS 24.04 LTS |

---

## Arquitectura de Dos Modelos

```
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9090 — Modelo Principal (12B, GPU, NGL=30)         │
│  Web UI: http://localhost:9090                              │
│  CTX=32768, 94 tools MCP                                   │
│  • Razonamiento complejo                                    │
│  • Delega tools simples → Sub-agente                        │
│  • "Hazlo tú mismo" → ejecuta directamente                  │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ delegate_to_subagent
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9091 — Sub-agente E4B (CPU, NGL=0)                 │
│  Web UI: http://localhost:9091                              │
│  CTX=8192                                                   │
│  • Spotify, Kasa, system info                               │
│  • Acceso directo del usuario                               │
│  • Respuestas rápidas                                       │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ Open WebUI (alternativa)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9092 — Open WebUI                                  │
│  http://localhost:9092                                      │
│  Interface tipo ChatGPT                                     │
└─────────────────────────────────────────────────────────────┘
```

---

## Modelos Disponibles

| Modelo | Puerto | GPU Layers | Velocidad | VRAM | CTX |
|---|---|---|---|---|---|
| **12B** (principal) | 9090 | 30 (GPU) | ~16 t/s | ~6GB | 32768 |
| **E4B** (sub-agente) | 9091 | 0 (CPU) | ~42 t/s | 0MB | 8192 |
| **26B** | 9090 | 0 (CPU) | ~1-3 t/s | N/A | 16384 |

> **Nota:** Los modelos MoE de 26B (128 experts) no pueden usar GPU offload.

---

## Estructura de Archivos

```
~/
├── llama.cpp/
│   ├── ai-models/              # Modelos GGUF
│   │   ├── google_gemma-4-E4B-it-Q4_K_M.gguf      (5GB)
│   │   ├── gemma-4-12b-it-Q4_K_M.gguf              (6.7GB)
│   │   ├── google_gemma-4-26B-A4B-it-Q4_K_M.gguf   (17GB)
│   │   └── gemma-4-26B_q4_0-it.gguf                (14.4GB)
│   └── build/bin/              # Binarios compilados
├── scripting/gpu-tools/        # Scripts de gestión
│   ├── gemma4-ctl.sh           # Control del servidor principal
│   ├── e4b-ctl.sh              # Control del sub-agente
│   ├── skills/                 # Tools MCP y asistente
│   │   ├── system_mcp_server.py    # 94 tools MCP
│   │   ├── kasa_mcp_server.py      # Tools Kasa
│   │   ├── assistant.py            # LLM + tool calling + TTS
│   │   ├── voice_hub.py            # Wake word + push-to-talk
│   │   └── tts_notifier.py         # Piper TTS
│   └── README.md               # Esta documentación
└── .config/
    ├── gemma4-server.conf      # Config modelo principal
    ├── e4b-server.conf         # Config sub-agente
    ├── system-prompt.txt       # System prompt con keywords
    ├── ai-memory.db            # Base de datos SQLite (memoria)
    ├── mcp-servers.json        # Config MCP servers
    └── notes/                  # Notas rápidas
        ├── General/
        ├── Trabajo/
        ├── Personal/
        └── Tasks/
```

---

## Sistema de Delegación

El modelo principal decide automáticamente cuándo delegar:

| Frase del usuario | Comportamiento |
|-------------------|----------------|
| "Pon música" | Delega al sub-agente E4B |
| "Enciende la luz" | Delega al sub-agente E4B |
| "Tú mismo" | Ejecuta directamente (sin delegar) |
| "No delegues" | Ejecuta directamente |
| "Hazlo tú" | Ejecuta directamente |

---

## Memoria Persistente

Sistema de memoria con SQLite para mantener contexto entre sesiones.

### Categorías

| Categoría | Descripción |
|-----------|-------------|
| `note` | Notas rápidas |
| `fact` | Hechos sobre el usuario |
| `preference` | Preferencias (música, apps, etc.) |
| `context` | Contexto de conversaciones |
| `task` | Tareas pendientes |

### Tools de Memoria

| Tool | Descripción |
|------|-------------|
| `memory_save` | Guardar entrada en memoria |
| `memory_search` | Buscar por texto o tags |
| `memory_context` | Obtener contexto relevante |
| `memory_list` | Listar entradas recientes |
| `memory_delete` | Eliminar entrada por ID |

### Base de Datos

Ubicación: `~/.config/ai-memory.db`

---

## Tools MCP (39 total)

### Smart Home
| Tool | Descripción |
|------|-------------|
| `kasa_set_plug_state` | Encender/apagar enchufes |
| `kasa_get_plugs_status` | Ver estado de enchufes |

### Sistema
| Tool | Descripción |
|------|-------------|
| `system_list_directory` | Navegar directorios |
| `system_file_info` | Metadata de archivos |
| `system_search_files` | Buscar archivos por patrón |
| `system_read_file` | Leer contenido de archivos |
| `system_write_file` | Escribir/crear archivos |
| `system_run_command` | Ejecutar comandos |
| `system_get_system_info` | CPU, RAM, disco, OS |
| `system_get_gpu_status` | GPU NVIDIA: VRAM, temperatura |
| `system_screenshot` | Capturar pantalla |
| `system_clipboard` | Copiar/pegar texto |
| `system_brightness` | Control de brillo |
| `system_weather` | Clima actual |
| `system_timer` | Temporizador/alarma |
| `system_notes` | Notas rápidas |

### Navegador
| Tool | Descripción |
|------|-------------|
| `system_web_search` | Buscar en DuckDuckGo |
| `system_open_url` | Abrir URL en navegador |
| `system_run_python_script` | Ejecutar código Python |

### Multimedia
| Tool | Descripción |
|------|-------------|
| `system_media_control` | Play, pause, next, prev, volume |
| `system_send_notification` | Notificación de escritorio |

### Spotify (10 tools)
| Tool | Descripción |
|------|-------------|
| `system_spotify_search` | Buscar canciones/artistas |
| `system_spotify_now` | Ver qué suena |
| `system_spotify_play` | Reanudar |
| `system_spotify_pause` | Pausar |
| `system_spotify_next` | Siguiente canción |
| `system_spotify_previous` | Canción anterior |
| `system_spotify_volume` | Ajustar volumen (0-100) |
| `system_spotify_playlists` | Listar playlists |
| `system_spotify_launch` | Abrir Spotify |
| `system_spotify_play_track` | Buscar y reproducir canción |
| `system_spotify_play_artist` | Reproducir artista |
| `system_spotify_play_playlist` | Reproducir playlist |

### Memoria
| Tool | Descripción |
|------|-------------|
| `memory_save` | Guardar en memoria |
| `memory_search` | Buscar en memoria |
| `memory_context` | Obtener contexto |
| `memory_list` | Listar entradas |
| `memory_delete` | Eliminar entrada |

### Delegación
| Tool | Descripción |
|------|-------------|
| `delegate_to_subagent` | Delegar tarea al sub-agente E4B |

---

## Modo Swap (3 modos)

El sistema soporta 3 modos de contexto:

| Modo | CTX | RAM | Uso |
|------|-----|-----|-----|
| `swap off` | 16384 | ~8GB | Predeterminado, hibernación completa |
| `swap on` | 32768 | ~14GB | Contexto mayor, hibernación limitada |
| `swap aggressive` | 65536 | ~28GB | Contexto máximo, sin hibernación |

```bash
~/scripting/gpu-tools/gemma4-ctl.sh swap off      # CTX=16384
~/scripting/gpu-tools/gemma4-ctl.sh swap on       # CTX=32768
~/scripting/gpu-tools/gemma4-ctl.sh swap aggressive # CTX=65536
~/scripting/gpu-tools/gemma4-ctl.sh swap status    # Ver estado
```

---

## Servicios Systemd

### Modelo Principal (puerto 9090)

```bash
# Estado
systemctl --user status gemma4-server.service

# Control
~/scripting/gpu-tools/gemma4-ctl.sh start|stop|restart|status|logs

# Cambiar modelo
~/scripting/gpu-tools/gemma4-ctl.sh switch e4b|12b|26b
```

### Sub-agente E4B (puerto 9091)

```bash
# Estado
systemctl --user status e4b-server.service

# Control
~/scripting/gpu-tools/e4b-ctl.sh start|stop|restart|status|logs
```

### Open WebUI (puerto 9092)

```bash
# Iniciar
cd ~/docker/open-webui && sudo docker-compose up -d

# Detener
cd ~/docker/open-webui && sudo docker-compose down
```

---

## API OpenAI-compatible

### Modelo Principal (9090)

```bash
curl http://localhost:9090/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4",
    "messages": [{"role": "user", "content": "Hola"}]
  }'
```

### Sub-agente E4B (9091)

```bash
curl http://localhost:9091/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemma-4-e4b",
    "messages": [{"role": "user", "content": "Hola"}]
  }'
```

### Python

```python
from openai import OpenAI

# Modelo principal
client = OpenAI(base_url="http://localhost:9090/v1", api_key="none")
response = client.chat.completions.create(
    model="gemma-4",
    messages=[{"role": "user", "content": "Explica qué es CUDA"}]
)

# Sub-agente
client_e4b = OpenAI(base_url="http://localhost:9091/v1", api_key="none")
response = client_e4b.chat.completions.create(
    model="gemma-4-e4b",
    messages=[{"role": "user", "content": "Pon música"}]
)
```

---

## Configuración

### Modelo Principal

`~/.config/gemma4-server.conf`:

```bash
MODEL_PATH=/home/darkseid/llama.cpp/ai-models/gemma-4-12b-it-Q4_K_M.gguf
NGL=30                    # GPU layers
HOST=0.0.0.0
PORT=9090
CTX_SIZE_NORMAL=16384
CTX_SIZE_SWAP=32768
CTX_SIZE_AGGRESSIVE=65536
USE_SWAP=true
SWAP_AGGRESSIVE=false
```

### Sub-agente E4B

`~/.config/e4b-server.conf`:

```bash
MODEL_PATH=/home/darkseid/llama.cpp/ai-models/google_gemma-4-E4B-it-Q4_K_M.gguf
NGL=0                     # CPU-only
HOST=0.0.0.0
PORT=9091
CTX_SIZE=8192
```

---

## Comandos Rápidos

| Acción | Comando |
|---|---|
| **GPU** | |
| Ver estado GPU | `~/scripting/gpu-tools/gpu-status.sh` |
| Activar rendimiento | `~/scripting/gpu-tools/gpu-performance.sh --on` |
| Monitorear GPU | `~/scripting/gpu-tools/gpu-monitor.sh` |
| **Modelo Principal** | |
| Estado | `~/scripting/gpu-tools/gemma4-ctl.sh status` |
| Cambiar modelo | `~/scripting/gpu-tools/gemma4-ctl.sh switch e4b` |
| Modo swap | `~/scripting/gpu-tools/gemma4-ctl.sh swap on` |
| Logs | `~/scripting/gpu-tools/gemma4-ctl.sh logs` |
| **Sub-agente** | |
| Estado | `~/scripting/gpu-tools/e4b-ctl.sh status` |
| Iniciar | `~/scripting/gpu-tools/e4b-ctl.sh start` |
| Logs | `~/scripting/gpu-tools/e4b-ctl.sh logs` |
| **Open WebUI** | |
| URL | `http://localhost:9092` |
| API URL | `http://172.17.0.1:9090/v1` |
| **Whisper STT** | |
| Estado | `systemctl --user status whisper-server.service` |
| URL | `http://localhost:9093` |
| API | `http://localhost:9093/v1/audio/transcriptions` |

---

## Voice Input (Speech-to-Text)

Sistema de transcripción de voz con Whisper local.

### Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9093 — Whisper API Server                          │
│  Endpoint: http://localhost:9093/v1/audio/transcriptions    │
│  Modelo: faster-whisper (base, CPU, int8)                  │
│  • OpenAI-compatible API                                   │
│  • Soporte para múltiples idiomas                          │
│  • VAD (Voice Activity Detection)                          │
└─────────────────────────────────────────────────────────────┘
```

### Servicios

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| Modelo Principal | 9090 | Gemma 4 12B (GPU) |
| Sub-agente E4B | 9091 | Gemma 4 E4B (CPU) |
| Open WebUI | 9092 | Interface web |
| **Whisper STT** | **9093** | **Speech-to-Text** |

### Control del Servicio Whisper

```bash
# Estado
systemctl --user status whisper-server.service

# Iniciar
systemctl --user start whisper-server.service

# Detener
systemctl --user stop whisper-server.service

# Logs
journalctl --user -u whisper-server.service -f
```

### Configurar en Open WebUI

1. Abre `http://localhost:9092`
2. Ve a Settings (⚙️) > Audio
3. En **Speech-to-Text (STT)**:
   - Selecciona "Whisper" o "OpenAI"
   - URL: `http://localhost:9093/v1`
4. Guarda los cambios

### API Endpoint

```bash
# Transcribir archivo de audio
curl -X POST http://localhost:9093/v1/audio/transcriptions \
  -F "file=@audio.wav" \
  -F "language=es"

# Respuesta
{"text": "Transcripción del audio", "language": "es", "duration": 5.2}
```

---

## Solución de Problemas

### Servidor no arranca

```bash
systemctl --user status gemma4-server.service
journalctl --user -u gemma4-server.service -n 50
```

### VRAM insuficiente

```bash
# Reducir GPU layers
~/scripting/gpu-tools/gemma4-ctl.sh swap off

# O cambiar a modo CPU-only
~/scripting/gpu-tools/gemma4-ctl.sh switch 26b
```

### Sub-agente no responde

```bash
# Verificar puerto
lsof -i :9091

# Reiniciar
~/scripting/gpu-tools/e4b-ctl.sh restart
```

### Tools no aparecen

```bash
# Verificar MCP server
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' | python3 ~/scripting/gpu-tools/skills/system_mcp_server.py
```
