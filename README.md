# AI Lab — Local AI + Voice Assistant

Repositorio de configuración, scripts y documentación para un sistema completo de IA local con:
- GPU NVIDIA RTX 5060 Laptop
- llama.cpp (inferencia local)
- Gemma 4 (modelos de lenguaje)
- Voice Assistant (Whisper + Piper TTS)
- MCP Tools (39 herramientas)
- Open WebUI (interfaz web)

## Hardware

| Componente | Detalle |
|---|---|
| GPU | NVIDIA RTX 5060 Laptop (8GB VRAM) |
| RAM | 16GB |
| Driver | NVIDIA 580.173.02 (open kernel module) |
| CUDA | 12.0 |
| llama.cpp | v0.3.0-dev (b10688) |
| SO | Pop!_OS 24.04 LTS |

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9090 — Modelo Principal (12B, GPU, NGL=30)         │
│  Web UI: http://localhost:9090                              │
│  CTX=32768, 39 tools MCP                                   │
│  • Razonamiento complejo                                    │
│  • Delega tools simples → Sub-agente                        │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ delegate_to_subagent
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9091 — Sub-agente E4B (CPU, NGL=0)                 │
│  Web UI: http://localhost:9091                              │
│  CTX=8192                                                   │
│  • Spotify, Kasa, system info                               │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9092 — Open WebUI                                  │
│  http://localhost:9092                                      │
│  Interface tipo ChatGPT                                     │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9093 — Whisper STT                                 │
│  http://localhost:9093                                      │
│  Speech-to-Text (Voice Input)                               │
└─────────────────────────────────────────────────────────────┘
```

## Estructura del Repositorio

```
ai-lab/
├── configs/                    # Configuraciones
│   ├── gemma4-server.conf     # Config modelo principal
│   ├── e4b-server.conf        # Config sub-agente
│   ├── system-prompt.txt      # System prompt con keywords
│   ├── systemd/               # Servicios systemd
│   │   ├── gemma4-server.service
│   │   ├── e4b-server.service
│   │   └── whisper-server.service
│   └── mcp/                   # Config MCP
│       └── mcp-servers.json
├── scripts/                    # Scripts de gestión
│   ├── gpu/                   # GPU tools
│   │   ├── gpu-status.sh
│   │   ├── gpu-performance.sh
│   │   └── gpu-monitor.sh
│   ├── llama/                 # LLM servers
│   │   ├── gemma4-ctl.sh
│   │   └── e4b-ctl.sh
│   ├── voice/                 # Voice assistant
│   │   ├── assistant.py
│   │   ├── voice_hub.py
│   │   └── tts_notifier.py
│   └── tools/                 # MCP tools
│       ├── system_mcp_server.py
│       ├── kasa_mcp_server.py
│       └── whisper_server.py
├── docs/                       # Documentación
│   ├── README.md              # Documentación principal
│   ├── problems/              # Problemas encontrados
│   ├── solutions/             # Soluciones implementadas
│   └── changelog/             # Historial de cambios
├── models/                     # Modelos (no en git)
├── .gitignore
└── README.md                   # Este archivo
```

## Instalación Rápida

```bash
# 1. Clonar repositorio
git clone <url> ~/ai-lab
cd ~/ai-lab

# 2. Copiar configuraciones
cp configs/gemma4-server.conf ~/.config/
cp configs/e4b-server.conf ~/.config/
cp configs/system-prompt.txt ~/.config/
cp configs/mcp/mcp-servers.json ~/.config/
cp configs/systemd/* ~/.config/systemd/user/

# 3. Copiar scripts
cp scripts/llama/* ~/scripting/gpu-tools/
cp scripts/tools/* ~/scripting/gpu-tools/skills/
cp scripts/voice/* ~/scripting/gpu-tools/skills/
cp scripts/gpu/* ~/scripting/gpu-tools/

# 4. Recargar systemd
systemctl --user daemon-reload

# 5. Iniciar servicios
systemctl --user start gemma4-server.service
systemctl --user start e4b-server.service
systemctl --user start whisper-server.service
```

## Servicios

| Servicio | Puerto | Descripción |
|----------|--------|-------------|
| Modelo Principal | 9090 | Gemma 4 12B (GPU) |
| Sub-agente E4B | 9091 | Gemma 4 E4B (CPU) |
| Open WebUI | 9092 | Interface web |
| Whisper STT | 9093 | Speech-to-Text |

## Tools MCP (39 total)

### Smart Home
- `kasa_set_plug_state` — Encender/apagar enchufes
- `kasa_get_plugs_status` — Ver estado de enchufes

### Sistema
- `system_list_directory` — Navegar directorios
- `system_file_info` — Metadata de archivos
- `system_search_files` — Buscar archivos
- `system_read_file` — Leer archivos
- `system_write_file` — Escribir archivos
- `system_run_command` — Ejecutar comandos
- `system_get_system_info` — Info del sistema
- `system_get_gpu_status` — Estado GPU
- `system_screenshot` — Capturar pantalla
- `system_clipboard` — Copiar/pegar texto
- `system_brightness` — Control brillo
- `system_weather` — Clima actual
- `system_timer` — Temporizador
- `system_notes` — Notas rápidas

### Navegador
- `system_web_search` — Buscar en DuckDuckGo
- `system_open_url` — Abrir URL
- `system_run_python_script` — Ejecutar Python

### Multimedia
- `system_media_control` — Play/pause/volume
- `system_send_notification` — Notificaciones

### Spotify
- `system_spotify_search` — Buscar
- `system_spotify_now` — Ver qué suena
- `system_spotify_play` — Reanudar
- `system_spotify_pause` — Pausar
- `system_spotify_next` — Siguiente
- `system_spotify_previous` — Anterior
- `system_spotify_volume` — Volumen
- `system_spotify_playlists` — Playlists
- `system_spotify_launch` — Abrir Spotify
- `system_spotify_play_track` — Reproducir canción
- `system_spotify_play_artist` — Reproducir artista
- `system_spotify_play_playlist` — Reproducir playlist

### Memoria
- `memory_save` — Guardar en memoria
- `memory_search` — Buscar en memoria
- `memory_context` — Obtener contexto
- `memory_list` — Listar entradas
- `memory_delete` — Eliminar entrada

### Delegación
- `delegate_to_subagent` — Delegar al sub-agente

## Problemas y Soluciones

### GPU en D3cold
**Problema:** GPU entra en estado de bajo consumo y no responde.
**Solución:** 
```bash
~/scripting/gpu-tools/gpu-performance.sh --on
```

### CUDA OOM con CTX grande
**Problema:** CTX=32768 con NGL=40 causa crash por VRAM insuficiente.
**Solución:** Reducir NGL a 30, usar modo swap.

### MCP Server no carga tools
**Problema:** Servidor MCP falla al iniciar.
**Solución:** Verificar Python path y dependencias.

### Voice Input no funciona
**Problema:** Whisper no está instalado.
**Solución:** Instalar faster-whisper y crear API server.

## Changelog

### v1.0.0 (2026-08-29)
- Sistema base con GPU NVIDIA RTX 5060
- llama.cpp v0.3.0-dev
- Gemma 4 12B (principal) + E4B (sub-agente)
- 39 tools MCP
- Sistema de memoria persistente (SQLite)
- Voice input con Whisper
- Open WebUI en puerto 9092

## Licencia

Proyecto personal de configuración de IA local.
