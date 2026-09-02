# AI Lab — Local AI + Voice Assistant

Sistema completo de IA local con GPU NVIDIA, modelos Gemma 4, asistente de voz, MCP tools y compartir chats.

## Hardware

| Componente | Detalle |
|---|---|
| GPU | NVIDIA RTX 5060 Laptop (8GB VRAM) |
| RAM | 16GB (~14GiB usables) |
| Driver | NVIDIA 580.173.02 (open kernel module) |
| CUDA | 13.0 (Driver) / 12.0 (Toolkit) |
| llama.cpp | v0.3.0-dev (b10688, commit c589f0ed1) |
| SO | Pop!_OS 24.04 LTS |
| Swap | 42GB (14.9GB ZRAM + 27.2GB NVMe, swappiness=180) |

## Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9090 — Modelo Principal Gemma 4 12B (GPU, NGL=30)   │
│  Web UI: http://localhost:9090                              │
│  CTX=32768, 248 tools MCP (modulares)                      │
│  • Razonamiento complejo, planning y auto-ejecución         │
│  • Visualización local multimedia (media_view)              │
│  • Delega tools simples → Sub-agente E4B                    │
│  • Orquestador: mcp_server.py (18 domain modules)          │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ delegate_to_subagent
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9091 — Sub-agente E4B (CPU, NGL=0)                 │
│  Web UI: http://localhost:9091                              │
│  CTX=8192                                                   │
│  • Spotify, Kasa, system info, OSINT                        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9092 — Open WebUI                                  │
│  http://localhost:9092                                      │
│  Interface tipo ChatGPT con chat y extensiones              │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9093 — Whisper STT                                 │
│  http://localhost:9093                                      │
│  Speech-to-Text en tiempo real para asistente de voz        │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Puerto 9095 — ChatShare & Servidor Multimedia Local        │
│  http://localhost:9095                                      │
│  • Streaming multimedia local (imágenes, audio, video)      │
│  • Gestión de chats locales (SQLite + Alembic)              │
│  • Sync automático con VPS (ai.castelancarpinteyro.com)     │
│  • Generación de tokens seguros y códigos QR                │
└─────────────────────────────────────────────────────────────┘
                           │
                           │ r2_upload / chat_export
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Cloudflare R2 Object Storage (CDN Global, $0 Egress)       │
│  https://pub-1e0feaec3fa0410fa72dfccb31f05917.r2.dev       │
│  • Distribución CDN de multimedia sin saturar el VPS        │
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
| Telegram Bot | - | Bot Asistente IA (Voz, Visión, Tools) | `telegram-bot.service` |

### Comandos de Gestión

```bash
# Modelo Principal (12B GPU)
~/scripting/gpu-tools/gemma4-ctl.sh start|stop|restart|status|logs

# Sub-agente E4B (CPU)
~/scripting/gpu-tools/e4b-ctl.sh start|stop|restart|status|logs

# Telegram Bot
~/scripting/gpu-tools/telegram-ctl.sh start|stop|restart|status|logs|set-token|allow-user

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

## Tools MCP (248 herramientas modulares)

### Local Media Viewing (1)
- `media_view` — Visualizar imágenes, audios y videos locales en el chat web (:9090) con Base64 Data-URI / streaming sin requerir internet.

### Cloudflare R2 Storage (4)
- `r2_upload` — Subir archivo local a Cloudflare R2 CDN ($0 costo de egress).
- `r2_list` — Listar archivos almacenados en el bucket de R2.
- `r2_delete` — Eliminar archivo de Cloudflare R2.
- `r2_status` — Diagnóstico y verificación de conexión con Cloudflare R2.

### ChatShare & Public Sharing (4)
- `chat_export` — Guardar y exportar conversación completa (con multimedia, reasoning y planning) a `ai.castelancarpinteyro.com` con código QR visual para escaneo móvil.
- `chat_share` — Generar enlace público con token de expiración configurable.
- `chat_list_shared` — Listar chats registrados.
- `chat_get_shared` — Obtener historial completo de un chat por su ID.

### Recordatorios & Temporizadores Omnicanal (3)
- `reminder_add` — Programa recordatorios y temporizadores con lenguaje natural y despacho multicanal (Telegram, escritorio, aviso visual).
- `reminder_list` — Lista recordatorios pendientes con tiempo restante y fecha exacta.
- `reminder_cancel` — Cancela o elimina un recordatorio por ID.

### Dev Ops & Control Remoto del Sistema (4)
- `dev_system_telemetry` — Dashboard en tiempo real de GPU NVIDIA (VRAM, temp, watts), CPU, RAM, Swap, Disco y servicios IA.
- `dev_service_control` — Gestión remota de servicios systemd (`gemma4-server`, `e4b-server`, `whisper-server`, `telegram-bot`, `git-sentinel`).
- `dev_process_monitor` — Monitoreo de procesos principales en consumo de CPU y memoria RAM.
- `dev_git_quick_action` — Acciones git rápidas (`status`, `diff`, `log`, `branch`, `pull`) en el acervo de repositorios.

### Procesamiento de Audio & Video con Whisper y yt-dlp (3)
- `media_download_url` — Descarga audio (MP3) o video (MP4) de YouTube, X, TikTok, Reddit o Podcasts con `yt-dlp`.
- `media_transcribe_audio` — Transcripción local automática de habla con Whisper STT (:9093).
- `media_summarize_content` — Resumen inteligente estructurado con Gemma 4 para videos de YouTube y audios largos.

### Generación de Voz Creativa de Alta Fidelidad (Kokoro-82M) (3)
- `voice_creative_generate` — Síntesis de voz expresiva y de estudio en CPU (Voz principal: `em_santa` en español).
- `voice_speak_notification` — Emite avisos hablados por los altavoces de la PC (`bm_george` en inglés británico o `em_santa` en español) con animación de teclado ASUS.
- `voice_creative_list` — Catálogo de voces masculinas, femeninas y narradores en español e inglés.

### Generación de Imagen por Difusión Local (1)
- `image_ai_generate` — Generación de imágenes artísticas, realistas y conceptuales con IA en CPU / Shared Memory y ComfyUI API.

### Smart Home, Iluminación & Automatizaciones (6)
- `execute_sleep_routine` — Rutina de dormir inteligente: apaga Lux, asegura carga en ElektroDante y apaga teclado (o apaga el equipo con `shutdown 0`).
- `trigger_visual_alert` — Avisos visuales y coreografías de color en teclado ASUS y lámpara Lux (estilos temáticos, multi-color libre, presets y retorno a Cian).
- `control_keyboard_backlight` — Control de brillo del teclado ASUS ROG/TUF (`off`, `low`, `med`, `high`).
- `audit_git_repositories` — Auditoría masiva del acervo de código en `/media/darkseid/DATA/Repos` (uncommitted, unpushed, untracked).
- `kasa_set_plug_state` — Encender/apagar enchufes Kasa (`Lux`, `ElektroDante`, `todos`).
- `kasa_get_plugs_status` — Ver estado actual de todos los enchufes Kasa.

#### Sistema y Manipulación Quirúrgica de Archivos (17)
- `system_list_directory` — Navegar directorios
- `system_file_info` — Metadata de archivos
- `system_search_files` — Buscar archivos
- `system_read_file` — Leer archivos con soporte para rangos de líneas (`start_line`, `end_line`, `max_lines`)
- `system_write_file` — Crear archivos nuevos o sobreescritura total
- `system_append_to_file` — Anexión instantánea al final sin releer ni sobreescribir el archivo previo (100x más eficiente)
- `system_replace_file_content` — Reemplazo quirúrgico exacto de bloques de texto sin alterar el resto del archivo
- `system_compact_context` — Compacta historiales conversacionales y contextos extensos al 15-20% preservando decisiones clave
- `system_run_command` — Ejecutar comandos (con destello dinámico en teclado)
- `system_get_system_info` — Info del sistema
- `system_get_gpu_status` — Estado GPU
- `system_screenshot` — Capturar pantalla
- `system_clipboard` — Copiar/pegar texto
- `system_brightness` — Control brillo
- `system_weather` — Clima actual
- `system_timer` — Temporizador
- `system_notes` — Notas rápidas

### Navegador (3)
- `system_web_search` — Búsqueda web (DuckDuckGo libre)
- `system_open_url` — Abrir URL
- `system_run_python` — Ejecutar script Python

### Multimedia (2)
- `system_volume` — Control de volumen
- `system_media_control` — Play/pause/next/prev

### Spotify (12)
- `system_spotify_status` — Estado actual
- `system_spotify_play` — Reproducir
- `system_spotify_pause` — Pausar
- `system_spotify_next` — Siguiente
- `system_spotify_previous` — Anterior
- `system_spotify_volume` — Volumen
- `system_spotify_playlists` — Playlists
- `system_spotify_launch` — Abrir Spotify
- `system_spotify_play_track` — Reproducir canción
- `system_spotify_play_artist` — Reproducir artista
- `system_spotify_play_playlist` — Reproducir playlist

### Memoria Inteligente y Contexto Persistente (6)
- `memory_save` — Guardar en memoria aplicando directiva de fragmentación atómica
- `memory_search` — Búsqueda tokenizada multitérmino con ranking de relevancia y entrega de contenido íntegro sin truncado
- `memory_get` — Recuperar entrada de memoria completa por su ID numérico
- `memory_context` — Obtener contexto de entradas recientes
- `memory_list` — Listar catálogo de entradas registradas
- `memory_delete` — Eliminar entrada por ID

### Delegación (1)
- `delegate_to_subagent` — Delegar al sub-agente E4B

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

### Email (11)
- `email_send` — Enviar correos vía SMTP (smtplib directo)
- `email_list` — Listar correos de una carpeta con paginación
- `email_read` — Leer un correo completo por ID
- `email_search` — Buscar correos por asunto, remitente o contenido
- `email_folders` — Listar carpetas disponibles en el servidor
- `email_mark_read` — Marcar un correo como leído
- `email_delete` — Eliminar un correo por ID
- `email_configure` — Configurar credenciales SMTP/IMAP
- `email_test` — Probar configuración SMTP
- `email_discover_settings` — Auto-descubrir SMTP/IMAP por dominio
- `email_setup_wizard` — Wizard completo: descubre + configura + prueba

### Fútbol y Deportes (20)
- `football_search_matches` — Buscar partidos por fecha, liga o equipo
- `football_get_match` — Detalle completo de un partido
- `football_live_scores` — Marcadores en vivo en tiempo real
- `football_get_match_h2h` — Historial de enfrentamientos directos
- `football_get_match_lineups` — Alineaciones titulares y suplentes
- `football_get_match_shotmap` — Mapa de tiros de un partido
- `football_get_match_incidents` — Eventos del partido (goles, tarjetas)
- `football_search_teams` — Buscar equipos por nombre
- `football_get_team` — Info completa de un equipo
- `football_get_team_fixtures` — Calendario de próximos partidos
- `football_search_players` — Buscar jugadores por nombre
- `football_get_player` — Info completa de un jugador
- `football_get_player_stats` — Estadísticas detalladas
- `football_get_standings` — Clasificación de una liga
- `football_list_leagues` — Catálogo de ligas disponibles
- `football_list_seasons` — Temporadas disponibles por liga
- `football_compare_odds` — Comparar cuotas de casas de apuestas
- `football_get_predictions` — Pronósticos y predicciones de IA
- `football_list_venues` — Estadios disponibles
- `football_list_referees` — Árbitros registrados

### SSH (8)
- `ssh_connect` — Ejecutar comandos remotos
- `ssh_copy` — Subir archivos vía SCP
- `ssh_fetch` — Descargar archivos vía SCP
- `ssh_sync` — Sincronizar directorios vía rsync
- `ssh_tunnel` — Crear túnel SSH con autossh
- `ssh_list_hosts` — Listar hosts SSH configurados
- `ssh_add_host` — Agregar host a SSH config
- `ssh_status` — Verificar estado de servidor remoto

### Comunicación (4)
- `send_notification` — Notificación de escritorio (opciones avanzadas)
- `notify_contextual` — Notificación contextual (la IA decide cuándo notificar)
- `format_whatsapp` — Formatear texto para WhatsApp (negritas, listas anidadas, emojis)
- `whatsapp_link` — Generar enlace wa.me con mensaje prellenado
- `format_email` — Componer cuerpo de email (plain/html/both)

### Web & Internet (12)
- `browse_web` — Obtener contenido de URL (text/html/json)
- `http_request` — Cliente HTTP (GET/POST/PUT/DELETE)
- `search_google` — Búsqueda en Google con AI Mode
- `search_news` — Buscar noticias (DuckDuckGo)
- `search_docs` — Buscar documentación técnica
- `search_sports` — Resultados deportivos en vivo
- `fetch_article` — Obtener artículo completo (BeautifulSoup)
- `search_with_content` — Buscar + obtener contenido del primer resultado
- `dns_lookup` — Consultas DNS (A/MX/TXT/NS/CNAME)
- `ssl_check` — Verificar certificado SSL
- `whois_lookup` — Consulta WHOIS de dominio

### Database (2)
- `sql_query` — Ejecutar queries SQL en SQLite
- `backup_database` — Backup de bases de datos SQLite

### Data Processing (7)
- `csv_to_json` — Convertir CSV a JSON
- `json_to_csv` — Convertir JSON a CSV
- `convert_file` — Conversión multi-formato (CSV/JSON/XML/YAML/MD)
- `extract_pdf` — Extraer texto de PDFs
- `generate_csv` — Generar CSV desde datos
- `data_analysis` — Análisis básico de datos

### System & Security (4)
- `log_analysis` — Analizar logs del sistema
- `generate_report` — Generar reportes Markdown
- `security_audit` — Auditoría básica de seguridad
- `secret_detection` — Escanear código en busca de secretos

### Planning (1)
- `plan_tasks` — Generar plan de tareas

### OSINT (5)
- `osint_username` — Buscar username en 3300+ plataformas (maigret/sherlock)
- `osint_email` — Investigar email para encontrar cuentas (holehe)
- `osint_domain` — Inteligencia de dominio (DNS, WHOIS, subdominios)
- `osint_ip` — Inteligencia de IP (geolocalización, ASN, reverse DNS)
- `osint_person` — Buscar persona por nombre en múltiples plataformas

### Auditoría y Trazabilidad (2)
- `audit_get_metrics` — Consulta métricas agregadas de rendimiento de tools, tasa de éxito, latencia y uso de GPU/VRAM.
- `audit_list_traces` — Lista las últimas trazas de ejecución registradas para trazabilidad y auto-diagnóstico.

### Flujos de Trabajo Declarativos (3)
- `workflow_list` — Listar pipelines DAG disponibles en configs/workflows/.
- `workflow_run` — Ejecutar pipeline multi-paso declarativo por nombre (ej. daily_briefing).
- `workflow_status` — Consultar estado y resultados por ID de ejecución.

### Memoria Vectorial y RAG Semántico (4)
- `vector_search` — Búsqueda semántica por similitud coseno sobre documentación, notas y código local.
- `vector_index_path` — Indexar carpetas o archivos en la base vectorial SQLite.
- `vector_remember` — Guardar hechos o preferencias del usuario en memoria episódica vectorial.
- `vector_stats` — Estadísticas de colecciones, fragmentos indexados y uso de almacenamiento.

### Navegación Web Headless & Sincronización Brave (12)
- `browser_navigate` — Navegar a URLs interactivas con Brave Browser headless.
- `browser_extract_text` — Extraer texto de elementos o selector CSS.
- `browser_extract_markdown` — Modo lectura: extraer contenido principal convertido a Markdown limpio.
- `browser_click` — Hacer clic en botones o enlaces interactivos.
- `browser_type` — Llenar formularios o escribir en inputs web.
- `browser_screenshot` — Captura de pantalla guardada en directorio multimedia lista para media_view.
- `browser_print_pdf` — Imprimir y exportar página web a documento PDF de alta fidelidad.
- `browser_get_links` — Extraer lista completa de hipervínculos de la página.
- `browser_list_tabs` — Listar pestañas abiertas en el navegador headless.
- `browser_sync_brave_profile` — Sincronizar cookies y sesiones autenticadas de Brave personal.
- `browser_clear_session` — Limpiar cookies y caché (modo incógnito / anónimo).
- `browser_status` — Consulta de URL activa, título y puerto CDP.

### Asistencia Visual de Escritorio Multi-Monitor (4)
- `desktop_context_explain` — Análisis contextual omnipotente: qué está haciendo el usuario en pantalla, botones/opciones y sugerencias paso a paso.
- `desktop_list_monitors` — Listar pantallas y monitores físicos conectados (xrandr), resoluciones y geometrías.
- `desktop_list_windows` — Listar ventanas abiertas en el escritorio, aplicaciones y estado de foco.
- `desktop_capture_region` — Captura de ventana activa, monitor concreto o región rectangular.

### Voz Bidireccional Full-Duplex, Diagnóstico & Perfiles (11)
- `voice_speak` — Sintetizar voz en tiempo real con soporte de interrupción (Barge-In).
- `voice_listen` — Escuchar micrófono con detección de actividad de voz (VAD) y auto-corte de silencio.
- `voice_status` — Estado de TTS, Whisper STT, micrófono y Barge-In.
- `voice_set_profile` — Personalizar perfil de voz, acento, idioma, velocidad y tono.
- `voice_list_profiles` — Listar todos los perfiles de voz, idiomas y acentos disponibles.
- `voice_conversational_turn` — Ejecutar ciclo conversacional continuo por voz con LLM local y Barge-In.
- `audio_check_volume` — Diagnosticar volumen y silencio con alertas si no es audible.
- `audio_set_volume` — Ajustar volumen y desmutear bocinas.
- `vision_analyze_image` — Análisis visual multimodal sobre imágenes locales o capturas.
- `vision_inspect_screen` — Captura de pantalla del escritorio en vivo y análisis visual.
- `vision_ocr` — Extracción óptica de texto (OCR) con Tesseract local.

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
| `/api/v1/media?path=...` | GET | Servir multimedia local (streaming CORS) |
| `/view/{id}?token={token}` | GET | Visor web público interactivo |

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

---

## Almacenamiento Cloudflare R2 (CDN Multimedia)

Cloudflare R2 proporciona almacenamiento de objetos compatible con S3 con **$0 costo de transferencia (egress libre)**, utilizado para servir capturas, audios de Piper TTS, grabaciones de voz de Whisper y videos sin recargar el disco del servidor VPS.

### Configuración (`~/.config/ai-lab/r2.env`)

```ini
R2_ACCOUNT_ID="1abad53de70fc4c8729b148f45cfc26c"
R2_ACCESS_KEY_ID="tu_access_key_id"
R2_SECRET_ACCESS_KEY="tu_secret_access_key"
R2_BUCKET_NAME="ai-lab"
R2_PUBLIC_DOMAIN="https://pub-1e0feaec3fa0410fa72dfccb31f05917.r2.dev"
```

### CLI `r2`

```bash
# Configurar credenciales
r2 configure --account-id ... --access-key ... --secret-key ... --bucket ai-lab

# Verificar estado y conexión S3
r2 status

# Subir archivo multimedia
r2 upload ~/screenshot.png --prefix screenshots

# Listar archivos
r2 list

# Eliminar archivo
r2 delete screenshots/screenshot.png
```

---

## Visualización Multimedia en el Chat

El sistema soporta dos modos de renderizado multimedia:

1. **Local en el Chat (:9090 / Open WebUI)** vía `media_view`:
   - Utiliza Data-URIs Base64 y streaming local desde el puerto `9095`.
   - Bypassea restricciones de COEP (`Cross-Origin-Embedder-Policy: require-corp`) en la interfaz web de `llama-server`.
   - No requiere conexión a internet ni subida a la nube.
2. **Público en la Web (`ai.castelancarpinteyro.com`)** vía `chat_export`:
   - Sube automáticamente las rutas locales a Cloudflare R2 CDN.
   - Genera enlace público de 72h con código QR interactivo para escaneo desde dispositivos móviles.
   - Renderiza reproductores nativos HTML5 de audio, video y visor Lightbox con zoom para imágenes.

---

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
│   ├── roadmap/               # Plan de evolución y fases (ROADMAP.md)
│   ├── problems/              # Problemas encontrados (PROBLEMS.md)
│   ├── solutions/             # Soluciones implementadas (SOLUTIONS.md)
│   └── changelog/             # Historial de cambios (CHANGELOG.md)
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

## Quickstart (rápido)

Sigue estos pasos para poner en marcha el sistema básico en una máquina local:

1. Clona el repositorio y sitúate en la carpeta del proyecto:

```bash
git clone git@github.com:dantecc10/ai-lab.git ~/ai-lab
cd ~/ai-lab
```

2. Copia las configuraciones a tu usuario (ajusta rutas según tu sistema):

```bash
mkdir -p ~/.config && cp configs/gemma4-server.conf ~/.config/
cp configs/e4b-server.conf ~/.config/
cp configs/system-prompt.txt ~/.config/
cp configs/mcp/mcp-servers.json ~/.config/
```

3. Prepara los scripts y entornos auxiliares:

```bash
mkdir -p ~/scripting/gpu-tools && cp scripts/llama/* ~/scripting/gpu-tools/
cd deploy/chatshare && python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

4. Recarga `systemd` de usuario y arranca los servicios principales:

```bash
systemctl --user daemon-reload
systemctl --user start gemma4-server.service e4b-server.service whisper-server.service chatmanager.service
```

5. Verifica que los servicios estén accesibles (puertos principales):

- Modelo principal: http://localhost:9090
- Sub-agente E4B: http://localhost:9091
- Open WebUI: http://localhost:9092
- Whisper STT: http://localhost:9093
- ChatShare: http://localhost:9095

---

## Contribuir

Gracias por querer contribuir. Para colaborar con la documentación o el código sigue estos pasos:

1. Haz fork del repositorio y crea una rama con un nombre descriptivo:

```bash
git checkout -b docs/actualizar-README
```

2. Realiza cambios pequeños y atómicos en la documentación dentro de la carpeta `docs/` o en `README.md`.

3. Añade pruebas o instrucciones reproducibles si cambias scripts o despliegues.

4. Haz commit con un mensaje claro y empuja tu rama:

```bash
git add docs/ README.md
git commit -m "docs: actualizar Quickstart y guía de contribución"
git push origin HEAD
```

5. Abre un Pull Request describiendo los cambios y el motivo. Si el cambio afecta a la operación del sistema, indica cómo probarlo localmente.

---

Para más detalles sobre problemas conocidos y soluciones, consulta el directorio `docs/`.

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

## Ajustes de Rendimiento y Suspensión

### 1. Suspensión S0ix (Modern Standby) y GPU Colgada en AMD/ASUS
En portátiles AMD con RTX serie 40/50, S0ix causa que la GPU quede atrapada en `D3cold` tras suspender. Se resuelve configurando en `/etc/modprobe.d/`:
```ini
# /etc/modprobe.d/nvidia-graphics-drivers-sleep.conf y system76-power.conf
options nvidia NVreg_EnableS0ixPowerManagement=0
options nvidia NVreg_PreserveVideoMemoryAllocations=1
options nvidia NVreg_TemporaryFilePath=/var/tmp
```

### 2. Despertar PCIe y Rendimiento GPU
```bash
# Activar máximo rendimiento (PCI rescan, persistence mode, d3cold off)
~/ai-lab/scripts/gpu/gpu-performance.sh --on

# Ver estado actual del bus y P-State
~/ai-lab/scripts/gpu/gpu-performance.sh --status
```

### 3. Persistencia de Servicios de Usuario (Linger)
Para evitar que `systemd --user` termine los procesos de IA al cerrar sesión o suspender:
```bash
sudo loginctl enable-linger $USER
```

---

## Solución de Problemas

### GPU en D3cold tras reposo
```bash
# Ejecutar script de despertar y re-escaneo PCI
~/ai-lab/scripts/gpu/gpu-performance.sh --on
```

### CUDA OOM con CTX grande (32K)
```bash
# Asegurar NGL=30 en ~/.config/gemma4-server.conf (libera ~2GB VRAM)
NGL=30
~/ai-lab/scripts/llama/gemma4-ctl.sh restart
```

### Servicio systemd no inicia o se detiene
```bash
# Habilitar linger y revisar logs
sudo loginctl enable-linger $USER
journalctl --user -u gemma4-server.service -f
```

### ChatShare no conecta con VPS
```bash
# Probar endpoint y revisar logs del demonio
curl -s https://ai.castelancarpinteyro.com/health
journalctl --user -u chatmanager.service -f
```

---

## Changelog

### v1.8.0 (2026-09-02)
- **Email Fix**: Reemplazado `msmtp` (subprocess timeout) con `smtplib.SMTP_SSL()` directo para envío de correos más confiable.
- **Sports API (20 tools)**: Integración completa de API BSD para fútbol: partidos en vivo, clasificaciones, pronósticos, cuotas, jugadores y más.
- **Email IMAP (6 tools)**: Lectura de correos vía IMAP — `email_list`, `email_read`, `email_search`, `email_folders`, `email_mark_read`, `email_delete`.
- **System Prompt Actualizado**: Incluye 248 herramientas con guías de uso (API vs web search), secciones de fútbol y email, políticas de seguridad actualizadas.
- Total tools: **222 → 248** (+20 fútbol, +6 email IMAP)

### v1.7.0 (2026-09-02)
- **Unified Audit System**: SQLite WAL mode, 7 herramientas de auditoría, dashboard web con Chart.js en `:9095/audit`.
- Total tools: **215 → 222**

### v1.6.0 (2026-09-02)
- **MCP Modular Architecture**: 18 domain modules + 6 shared utilities reemplazan monolito de 11,926 líneas.
- **Security Hardening**: SSRF blocking, path traversal prevention, command injection fixes.
- **12 crash fixes** across modules.
- Total tools: **215**

## Licencia

Proyecto personal de configuración de IA local.
