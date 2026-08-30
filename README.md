# AI Lab — Local AI + Voice Assistant

Sistema completo de IA local con GPU NVIDIA, modelos Gemma 4, asistente de voz, MCP tools y compartir chats.

## Hardware

| Componente | Detalle |
|---|---|
| GPU | NVIDIA RTX 5060 Laptop (8GB VRAM) |
| RAM | 16GB |
| Driver | NVIDIA 580.173.02 (open kernel module) |
| CUDA | 12.0 |
| llama.cpp | v0.3.0-dev (b10688, commit c589f0ed1) |
| SO | Pop!_OS 24.04 LTS |
| Swap | ~42GB |

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9090 — Modelo Principal (12B, GPU, NGL=30)         │
│  Web UI: http://localhost:9090                              │
│  CTX=32768, 94 tools MCP                                   │
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
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9095 — ChatShare Local                             │
│  http://localhost:9095                                      │
│  • Gestión de chats (SQLite + Alembic)                      │
│  • Tokens de acceso con expiración                          │
│  • Sync automático con VPS                                  │
│  • MCP tools para la IA                                     │
└─────────────────────────────────────────────────────────────┘
```

## Servicios

| Servicio | Puerto | Descripción | Systemd Service |
|----------|--------|-------------|-----------------|
| Modelo Principal | 9090 | Gemma 4 12B (GPU) | `gemma4-server.service` |
| Sub-agente E4B | 9091 | Gemma 4 E4B (CPU) | `e4b-server.service` |
| Open WebUI | 9092 | Interface web | Docker |
| Whisper STT | 9093 | Speech-to-Text | `whisper-server.service` |
| ChatShare | 9095 | Compartir chats | `chatmanager.service` |

### Comandos de Gestión

```bash
# Modelo Principal (12B GPU)
~/scripting/gpu-tools/gemma4-ctl.sh start|stop|restart|status|logs

# Sub-agente E4B (CPU)
~/scripting/gpu-tools/e4b-ctl.sh start|stop|restart|status|logs

# ChatShare
systemctl --user start|stop|restart|status chatmanager.service
journalctl --user -u chatmanager.service -f

# GPU
nvidia-smi
cat /sys/module/nvidia_drm/parameters/d3cold_disable
cat /sys/module/nvidia/parameters/NVreg_PreserveVideoMemoryAllocations
```

## Modelos

| Modelo | Archivo | VRAM | Uso |
|--------|---------|------|-----|
| Gemma 4 12B | `gemma-4-12b-it-Q4_K_M.gguf` | ~6141MB | Principal (GPU) |
| Gemma 4 E4B | `gemma-4-E4B-it-Q8_0.gguf` | ~5.1GB | Sub-agente (CPU) |
| Gemma 4 26B | `gemma-4-26b-it-Q4_0.gguf` | ~16GB | Alternativo (CPU) |
| Gemma 4 31B | `gemma-4-31B-it-Q4_0.gguf` | ~18GB | Alternativo (CPU) |

Ubicación: `~/llama.cpp/ai-models/`

## Tools MCP (94 total)

### Smart Home (2)
- `kasa_set_plug_state` — Encender/apagar enchufes
- `kasa_get_plugs_status` — Ver estado de enchufes

### Sistema (14)
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

### Navegador (3)
- `system_web_search` — Buscar en DuckDuckGo
- `system_open_url` — Abrir URL
- `system_run_python_script` — Ejecutar Python

### Multimedia (2)
- `system_media_control` — Play/pause/volume
- `system_send_notification` — Notificaciones

### Spotify (12)
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

### Memoria (5)
- `memory_save` — Guardar en memoria
- `memory_search` — Buscar en memoria
- `memory_context` — Obtener contexto
- `memory_list` — Listar entradas
- `memory_delete` — Eliminar entrada

### Delegación (1)
- `delegate_to_subagent` — Delegar al sub-agente

### ChatShare (9)
- `chat_create` — Crear nuevo chat
- `chat_list` — Listar chats
- `chat_get` — Obtener chat con mensajes
- `chat_edit` — Editar chat (crea versión)
- `chat_delete` — Soft delete
- `chat_versions` — Ver historial de versiones
- `chat_branch` — Crear rama
- `chat_share` — Compartir chat (genera token)
- `token_revoke` — Revocar token de acceso

### GitHub (16)
- `gh_repos_list`, `gh_repo_info`, `gh_repo_create`
- `gh_issues_list`, `gh_issue_create`
- `gh_pr_list`, `gh_pr_create`, `gh_pr_merge`
- `gh_actions_list`, `gh_actions_runs`
- `gh_release_list`, `gh_gist_list`, `gh_gist_create`
- `gh_search_repos`, `gh_search_code`

### Git (8)
- `git_status`, `git_log`, `git_diff`, `git_branches`
- `git_commit`, `git_push`, `git_pull`, `git_clone`

### Code Analysis (3)
- `code_analyze`, `code_count_lines`, `code_search_pattern`

### Project (2)
- `project_dependencies`, `project_structure`

### Docker (3)
- `docker_ps`, `docker_logs`, `docker_images`

### Chat (3)
- `chat_export`, `chat_list_shared`, `chat_get_shared`

### System (4)
- `system_shutdown` — shutdown/reboot/suspend/hibernate
- `file_compress`, `file_extract`, `file_permissions`

### Network (4)
- `network_ping`, `network_ports`, `network_speed`, `network_info`

### Processes (3)
- `process_list`, `process_kill`, `process_search`

### Cron (3)
- `cron_list`, `cron_add`, `cron_delete`

### Audio (3)
- `audio_list_devices`, `audio_set_source`, `audio_set_source_input`

### Monitoring (4)
- `monitor_realtime`, `monitor_top_processes`, `disk_usage`, `disk_io`

## ChatShare

Sistema de compartir chats con gestión local y sincronización con VPS.

### Arquitectura Local-First

```
PC Local (SQLite)  ──sync──▶  VPS (API mínima)
     │                              │
     ├── Chats con versiones        ├── Solo lectura
     ├── Tokens de acceso           ├── Tokens válidos
     ├── Ramas (como git)           └── Enlaces públicos
     └── Soft delete
```

### API Endpoints (localhost:9095)

| Endpoint | Método | Descripción |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/chats` | GET/POST | Listar/crear chats |
| `/api/v1/chats/{id}` | GET/PUT/DELETE | Obtener/editar/eliminar |
| `/api/v1/chats/{id}/versions` | GET | Historial de versiones |
| `/api/v1/chats/{id}/branches` | POST | Crear rama |
| `/api/v1/chats/{id}/share` | POST | Compartir (genera token) |
| `/api/v1/tokens/{id}/revoke` | POST | Revocar token |
| `/view/{id}?token={token}` | GET | Ver chat compartido |

### Database

Ubicación: `~/.local/share/chatmanager/chats.db`

Tablas:
- `chats` — Chats con versiones y sync
- `chat_versions` — Historial de versiones
- `chat_branches` — Ramas (tipo git)
- `access_tokens` — Tokens de acceso con expiración
- `sync_queue` — Cola de sincronización (outbox pattern)

### Workers

- **Token Expiration**: Verifica tokens expirados cada 5 minutos
- **Sync**: Sincroniza chats con VPS cada 30 segundos

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
├── deploy/                     # Deployment
│   └── chatshare/             # VPS deployment
│       ├── Dockerfile
│       ├── docker-compose.yml
│       └── nginx-plesk.conf
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
git clone git@github.com:dantecc10/ai-lab.git ~/ai-lab
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

# 4. Instalar dependencias ChatShare
cd ~/chatshare && python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 5. Recargar systemd
systemctl --user daemon-reload

# 6. Iniciar servicios
systemctl --user start gemma4-server.service
systemctl --user start e4b-server.service
systemctl --user start whisper-server.service
systemctl --user start chatmanager.service
```

## Requisitos Previos

### Sistema
```bash
# NVIDIA drivers
sudo apt install nvidia-driver-580

# CUDA toolkit
sudo apt install nvidia-cuda-toolkit

# Python 3.12
sudo apt install python3.12 python3.12-venv

# Docker (para Open WebUI)
sudo apt install docker.io docker-compose
sudo usermod -aG docker $USER
```

### Python (para Voice Assistant)
```bash
pip install faster-whisper piper-tts numpy sounddevice pyaudio
```

### Python (para ChatShare)
```bash
cd ~/chatshare
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Solución de Problemas

### GPU en D3cold
```bash
# Verificar estado
cat /sys/module/nvidia_drm/parameters/d3cold_disable

# Deshabilitar D3cold
echo 1 | sudo tee /sys/module/nvidia_drm/parameters/d3cold_disable

# Forzar modo de rendimiento
sudo nvidia-smi -pm 1
sudo nvidia-smi -pl 55
```

### CUDA OOM con CTX grande
```bash
# Reducir NGL (en gemma4-server.conf)
NGL=30  # En vez de 40

# Usar modo swap
USE_SWAP=true
SWAP_AGGRESSIVE=false
```

### Servicio systemd no inicia
```bash
# Verificar logs
journalctl --user -u gemma4-server.service -f

# Verificar dependencias
systemctl --user status gemma4-server.service

# Recargar daemon
systemctl --user daemon-reload
```

### ChatShare no conecta con VPS
```bash
# Verificar configuración
cat ~/chatshare/.env

# Verificar logs
journalctl --user -u chatmanager.service -f

# Probar conexión
curl -s https://ai.castelancarpinteyro.com/health
```

## Changelog

### v1.1.0 (2026-08-30)
- ChatShare: sistema de compartir chats con tokens
- Local-first: SQLite + Alembic para gestión de chats
- Workers automáticos (expiración de tokens, sync con VPS)
- 9 herramientas MCP adicionales (total: 94)
- Puerto 9095 para ChatShare

### v1.0.0 (2026-08-29)
- Sistema base con GPU NVIDIA RTX 5060
- llama.cpp v0.3.0-dev
- Gemma 4 12B (principal) + E4B (sub-agente)
- 85 tools MCP
- Sistema de memoria persistente (SQLite)
- Voice input con Whisper
- Open WebUI en puerto 9092

## Licencia

Proyecto personal de configuración de IA local.
