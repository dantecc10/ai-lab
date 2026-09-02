# Changelog

Historial detallado de versiones, características, mejoras de rendimiento y correcciones del sistema AI Lab.

---

## [1.8.0] - 2026-09-02

### Sports API & Email IMAP Integration

- **Sports API (20 tools)**: Integración completa de API BSD para fútbol con 20 herramientas:
  - Partidos: `football_search_matches`, `football_get_match`, `football_live_scores`
  - Detalles: `football_get_match_h2h`, `football_get_match_lineups`, `football_get_match_shotmap`, `football_get_match_incidents`
  - Equipos: `football_search_teams`, `football_get_team`, `football_get_team_fixtures`
  - Jugadores: `football_search_players`, `football_get_player`, `football_get_player_stats`
  - Ligas: `football_get_standings`, `football_list_leagues`, `football_list_seasons`
  - Pronósticos: `football_compare_odds`, `football_get_predictions`
  - Infraestructura: `football_list_venues`, `football_list_referees`
  - Token seguro en `~/.config/sports-api/token` (chmod 600), carga via env var `BSD_API_TOKEN`

- **Email IMAP (6 new tools)**: Lectura de correos vía IMAP con auto-descubrimiento de configuración:
  - `email_list`: Listar correos de una carpeta con paginación
  - `email_read`: Leer un correo completo por ID
  - `email_search`: Buscar correos por asunto, remitente o contenido
  - `email_folders`: Listar carpetas disponibles
  - `email_mark_read`: Marcar correo como leído
  - `email_delete`: Eliminar correo por ID

- **Email SMTP Fix**: Reemplazado `msmtp` (subprocess timeout) con `smtplib.SMTP_SSL()` directo para envío más confiable

- **System Prompt Updated**: Incluye 248 herramientas con guías de uso:
  - Regla: fútbol/deportes → SIEMPRE usar API local, NO web_search
  - Regla: clima → usar `weather`, NO web_search
  - Regla: correos → usar herramientas `email_*`, NO web_search
  - Herramientas de seguridad actualizadas en `security-policies.conf`

- Total tools: **222 → 248** (+20 fútbol, +6 email IMAP)

---

## [1.7.0] - 2026-09-02

### Unified Audit System & Dashboard

- **`mcp_common/audit.py`**: New unified audit engine with SQLite (WAL mode), thread-local connection pooling, 3 tables: `tool_calls`, `security_events`, `system_errors`
- **`mcp_common/logging.py`**: Rewritten to delegate to audit.py — every handler call now records to SQLite + flat file backup
- **`mcp_common/security.py`**: `is_blocked_command()` and `is_safe_url()` now record security events to `security_events` table
- **`mcp_server.py`**: Replaced old `AuditLogger` with unified audit engine; fixed `_notify_config` scoping bug (moved to module level); added `rotate_old_records()` on startup (90 days retention)
- **7 new audit tools**: `audit_metrics`, `audit_recent`, `audit_search`, `audit_security`, `audit_errors`, `audit_tool_timeline`, `audit_rotate`
- **Dashboard web** at `http://localhost:9095/audit`: Real-time Chart.js dashboard with hourly timeline, top tools, success rate, security events, and recent errors (auto-refresh every 30s)
- **API endpoints**: `/audit/api/metrics`, `/audit/api/recent`, `/audit/api/security`, `/audit/api/errors`, `/audit/api/timeline`
- Total tools: **215 → 222** (7 new audit tools)

---

## [1.6.0] - 2026-09-02

### MCP Modular Architecture & Security Hardening

- **Orquestador MCP Modular (`scripts/tools/mcp_server.py`)**:
  - Reemplaza el monolito `system_mcp_server.py` (11,926 líneas) con 18 domain modules + 6 shared utilities.
  - Auto-discovery vía `pkgutil` — agregar un nuevo dominio es solo crear un archivo `.py` en `mcp_domain/`.
  - Dispatcher de handlers con introspección de firmas (`_call_handler`) que detecta automáticamente si un handler espera `args` dict o named params.
  - **215 herramientas MCP únicas** (eliminados 3 duplicados: `reminder_add`, `reminder_list`, `reminder_cancel`).

- **Seguridad (`mcp_common/security.py`)**:
  - `is_safe_url()` — bloqueo de SSRF: IPs privadas (`127.0.0.0/8`, `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, `169.254.0.0/16`) y esquemas no seguros (`file://`, `javascript:`, `data:`, `ftp://`).
  - `sanitize_path()` — prevención de path traversal con detección de `..`.
  - CSS selector sanitization en `browser.py` contra inyección JavaScript.
  - Fix de command injection en `_timer` (usa `json.dumps` para mensagem), `_process_kill` (list form + validación de señal/PID), `_system_shutdown` (list form).
  - Fix de shell injection en `chmod` (`os.chmod()` en lugar de `subprocess.run(shell=True)`).
  - Fix de shell injection en SSH tunnel (list form en lugar de string interpolation).
  - Headers sensibles filtrados en `http_request` (`Set-Cookie`, `Authorization`).

- **Correcciones Críticas (12 crashes)**:
  - `communication.py` — imports faltantes: `quote`, `encrypt_value`; función inexistente `tool_email_send` → `_email_send_handler`.
  - `chatshare.py` — `datetime` no importado.
  - `database.py` — `datetime` no importado.
  - `osint.py` — `sys` no importado.
  - `vector.py` — `Path` de `pathlib` no importado.
  - `delegation.py` — constantes `E4B_URL`/`E4B_MODEL` no definidas; funciones `tool_*` inexistentes reemplazadas por dispatch vía `HANDLERS` dict.
  - `devops.py` — `docker_logs` ahora lee stdout+stderr (antes solo leía stdout, pero los logs van a stderr).
  - `smart_home.py` — IPs duplicadas contradictorias en sleep routine (`.66`/`.71` para Lux) corregidas para usar `KASA_DEVICES` dict.
  - `smart_home.py` — daemon thread para shutdown reemplazado por `subprocess.Popen` directo.

- **Mejoras de Calidad**:
  - `browser.py` — `log_operation` añadido a los 12 handlers (antes cero auditoría).
  - `smart_home.py` — 3 tools duplicados removidos (pertenecen a `communication.py`).
  - Imports sin uso removidos en `vector.py`, `workflow.py`, `network.py`, `security_tools.py`.

### Estructura Modular

```
scripts/tools/
├── mcp_server.py              # Orquestador (245 líneas)
├── mcp_common/                # Utilidades compartidas
│   ├── paths.py               # Rutas HOME, safe_path, format_size
│   ├── crypto.py              # Fernet encrypt/decrypt
│   ├── security.py            # SSRF, path traversal, blocked commands
│   ├── logging.py             # Audit logging
│   ├── notifications.py       # Desktop notifications
│   └── keyboard.py            # ASUS ROG keyboard control
├── mcp_domain/                # 18 domain modules
│   ├── filesystem.py          # 13 tools — archivos y directorios
│   ├── system.py              # 21 tools — sistema, GPU, procesos
│   ├── memory.py              # 6 tools — memoria persistente
│   ├── spotify.py             # 12 tools — control de Spotify
│   ├── smart_home.py          # 21 tools — Kasa, teclado, sleep
│   ├── devops.py              # 31 tools — GitHub, Git, Docker, código
│   ├── network.py             # 11 tools — red, DNS, SSL, WHOIS
│   ├── voice_vision.py        # 21 tools — voz, visión, OCR
│   ├── web_search.py          # 9 tools — búsqueda web, HTTP
│   ├── browser.py             # 12 tools — navegación headless
│   ├── communication.py       # 13 tools — notificaciones, email, WhatsApp
│   ├── chatshare.py           # 9 tools — exportar chats, R2 storage
│   ├── database.py            # 9 tools — SQL, CSV, JSON, PDF
│   ├── security_tools.py      # 5 tools — auditoría, secret detection
│   ├── osint.py               # 5 tools — OSINT username/email/domain
│   ├── ssh.py                 # 8 tools — SSH, tunnels, sync
│   ├── workflow.py            # 3 tools — DAG pipelines
│   ├── vector.py              # 4 tools — búsqueda semántica RAG
│   └── delegation.py          # 2 tools — sub-agente E4B
└── system_mcp_server.py       # Monolito original (backup)
```

---

## [1.5.0] - 2026-08-31

### Universal Omnipotent Assistant: Multi-Monitor Vision, Audio Health & Voice Profiles
- **Motor de Inteligencia Visual de Escritorio Multi-Monitor (`scripts/vision/desktop_context_engine.py`)**:
  - Detección precisa de múltiples pantallas y geometrías mediante `xrandr` (`eDP-1`, `DP-2`, etc.).
  - Detección e inspección de ventanas activas, aplicaciones (WM_CLASS) y estado de foco mediante `wmctrl` y `xdotool`.
  - Captura granular por ventana activa, monitor concreto o región rectangular (bbox).
  - Inspección contextual ("¿Qué estoy haciendo y qué opciones tengo?"): análisis multimodal visual con extracción de botones, opciones, menús e integración cruzada con documentación local vía RAG.
- **Diagnóstico y Salud de Audio con Alertas Automáticas (`scripts/voice/audio_diagnostics.py`)**:
  - Verificación en tiempo real del volumen y silenciador (Mute) en PipeWire/PulseAudio (`pactl`, `wpctl`, `amixer`).
  - Detección proactiva de inaudibilidad y disparo de notificaciones de escritorio si las bocinas están muteadas o con volumen < 15%.
  - Herramientas para control y ajuste de volumen directo.
- **Personalización de Perfiles de Voz e Idiomas (`scripts/voice/voice_profiles.py`, `configs/voice-profile.conf`)**:
  - Soporte de perfiles fonéticos (Español México, Castellano España, Inglés US/UK, Asistente Rápido 1.25x).
  - Control dinámico de velocidad (rate), tono (pitch), volumen y selección de motor TTS.
- **Bucle Conversacional Autónomo Manos Libres (`scripts/voice/conversational_loop.py`)**:
  - Asistente de voz continuo fuera de la interfaz web (:9090): Escucha VAD -> Whisper STT (:9093) -> Gemma 4 -> Síntesis Piper/spd-say con interrupción instantánea (Barge-In).
- **Nuevas Herramientas MCP**:
  - `desktop_context_explain`, `desktop_list_monitors`, `desktop_list_windows`, `desktop_capture_region`
  - `audio_check_volume`, `audio_set_volume`
  - `voice_set_profile`, `voice_list_profiles`, `voice_conversational_turn`
  - *Catálogo total ampliado a 182 herramientas en el servidor central (184 con Kasa).*

## [1.4.0] - 2026-08-31

### Phase 5: Full-Duplex Voice (Barge-In) & Multimodal Vision
- **Motor de Voz Bidireccional Full-Duplex (`scripts/voice/full_duplex_engine.py`)**:
  - Reproducción de voz no bloqueante vía PipeWire/PulseAudio con capacidad de interrupción inmediata (Barge-In) en menos de 50ms al detectar voz del usuario.
  - Detección de actividad de voz (VAD) inteligente con auto-corte tras silencios configurables (800ms) para escucha natural sin tiempos fijos de espera.
  - Integración nativa con Piper TTS, Whisper STT (:9093) y fallback automático a Speech Dispatcher (`spd-say`).
- **Motor de Visión Multimodal Local & OCR (`scripts/vision/multimodal_vision.py`)**:
  - Inferencia visual multimodal con modelos nativos Gemma 4 sobre el servidor `llama-server` (:9090) mediante Base64 data-URIs.
  - Captura y análisis visual de la pantalla activa del escritorio (`vision_inspect_screen`).
  - Extracción y reconocimiento óptico de caracteres local de alta velocidad (`vision_ocr`) con Tesseract.
- **Nuevas Herramientas MCP de Voz y Visión**:
  - `voice_speak`, `voice_listen`, `voice_status`
  - `vision_analyze_image`, `vision_inspect_screen`, `vision_ocr`
  - *Catálogo total ampliado a 173 herramientas en servidor de sistema (175 total con Kasa).*

### Phase 4: Headless Web Browsing & Brave Identity Synchronization
- **Motor de Navegación Web Headless (`scripts/tools/browser_engine.py`)**:
  - Driver de control sobre Brave Browser a través de Chrome DevTools Protocol (CDP nativo en puerto `:9222`) vía WebSockets.
  - Sincronizador de Identidades (`BraveIdentitySync`) que clona cookies SQLite (`Network/Cookies`), Local Storage y sesiones autenticadas desde `~/.config/BraveSoftware/Brave-Browser/Default` hacia el entorno seguro de la IA (`~/.local/share/ai-lab/browser_profile/`).
  - Soporte de interacción con SPAs, envío de formularios, clics, ejecución de JS y capturas de pantalla de alta fidelidad guardadas automáticamente en el directorio multimedia para visualización directa.
- **Nuevas Herramientas MCP de Navegación**:
  - `browser_navigate`: Navegación a URLs con detección de carga y título.
  - `browser_extract_text`: Extracción limpia de texto por selector CSS.
  - `browser_click`: Clic en elementos interactivos con auto-scroll.
  - `browser_type`: Inyección de texto y envío de formularios.
  - `browser_screenshot`: Captura de pantalla (parcial o full-page) lista para `media_view`.
  - `browser_sync_brave_profile`: Sincronización de cookies e identidades de Brave.
  - `browser_status`: Estado en tiempo real del navegador y puerto CDP.
  - *Catálogo total ampliado a 162 herramientas en servidor de sistema (164 total con Kasa).*

### Phase 3: Semantic Vector Memory & Local RAG
- **Motor de Embeddings y Vector Store Local (`scripts/tools/vector_engine.py`)**:
  - Almacenamiento vectorial indexado en SQLite (`~/.local/share/ai-lab/vectors/vector_store.db`) con soporte para colecciones, metadatos y serialización binaria empaquetada.
  - Generador de embeddings densos normalizados L2 ejecutados en CPU con filtrado de stop-words y sub-token n-grams (0% de consumo en VRAM de GPU).
  - Segmentador inteligente (`DocumentChunker`) con soporte para sintaxis Markdown (respetando encabezados jerárquicos) y bloques de código fuente.
- **Nuevas Herramientas MCP de RAG y Memoria Semántica**:
  - `vector_search`: Búsqueda semántica de alta fidelidad por similitud coseno sobre documentación y código.
  - `vector_index_path`: Indexación recursiva de directorios o archivos locales al vuelo.
  - `vector_remember`: Persistencia de recuerdos episódicos y preferencias del usuario.
  - `vector_stats`: Métricas globales de la base vectorial (fragmentos, colecciones, espacio en disco).
  - *Catálogo total ampliado a 155 herramientas en servidor de sistema (157 total con Kasa).*

### Phase 2: Event-Driven Hub & Declarative DAG Workflows
- **Motor de Flujos Declarativos DAG (`scripts/automation/dag_runner.py`)**:
  - Ejecutor de pipelines multi-paso en YAML/JSON con resolución de dependencias, interpolación de variables `{{step.result}}` y base de datos de ejecuciones SQLite (`workflow_executions.db`).
  - Workflows pre-empaquetados: `daily_briefing.json` y `system_health_audit.json` en `configs/workflows/`.
- **Event Bus Reactivo (`scripts/automation/event_hub.py`)**:
  - File Watcher reactivo sobre `~/Downloads` y `~/ai-lab/incoming` con alertas automáticas.
  - Monitor térmico y de memoria para GPU NVIDIA (>82°C) y saturación de swap (>90%) con notificaciones nativas de escritorio.
  - Registro de eventos en `~/.local/share/ai-lab/event_history.db`.
  - Demonio systemd `configs/systemd/event-hub.service`.
- **Nuevas Herramientas MCP de Automatización**:
  - `workflow_list`: Lista pipelines disponibles.
  - `workflow_run`: Ejecuta un workflow declarativo por nombre.
  - `workflow_status`: Consulta el estado y resultados de un flujo por ID.
  - *Catálogo total ampliado a 151 herramientas en servidor de sistema (153 total con Kasa).*

### Phase 1: Execution Power, Guardrails & ReAct Loop
- **Guardrails & Control de Riesgo (`configs/security-policies.conf` y `scripts/tools/security_guard.py`)**:
  - Clasificación de herramientas por nivel de riesgo (`safe`, `medium`, `high_risk`, `blocked`).
  - Bloqueo preventivo de comandos destructivos irreversibles (fork bombs, `rm -rf /`, `mkfs`, etc.).
  - Intercepción y confirmación interactiva para operaciones críticas del sistema.
- **Motor de Auditoría y Trazabilidad Local (`scripts/tools/audit_logger.py`)**:
  - Base de datos SQLite dedicada (`~/.local/share/ai-lab/audit_traces.db`) registrando latencia por herramienta, tokens estimados, tasa de éxito y métricas de VRAM/GPU.
  - Nuevas herramientas MCP: `audit_get_metrics` y `audit_list_traces` (Catálogo ampliado a 148 tools en servidor de sistema, 150 totales con Kasa).
- **Asistente ReAct con Auto-Corrección (`scripts/mcp_assistant.py` v2.0)**:
  - Bucle autónomo ReAct con reflexión sobre errores de ejecución (`--auto`, `--safe-mode`, `--max-steps`).
  - Visualización enriquecida con badges de riesgo en tiempo real (`[SAFE]`, `[MEDIUM]`, `[HIGH RISK]`).
  - Comandos interactivos `/metrics`, `/traces`, `/policy` para auto-diagnóstico.
- **Roadmap & Soluciones**:
  - Publicación del plan técnico en 5 fases en `docs/roadmap/ROADMAP.md`.
  - Publicación de la guía de patrones y soluciones técnicas en `docs/solutions/SOLUTIONS.md`.

---

## [1.3.0] - 2026-08-30

### Performance & Suspension Optimizations
- **Bypass de S0ix (Modern Standby)**: Desactivación de `NVreg_EnableS0ixPowerManagement=0` en `/etc/modprobe.d/` para prevenir el bloqueo de la GPU NVIDIA RTX 5060 en estado `D3cold` irrecuperable al despertar en plataformas AMD/ASUS.
- **Preservación de VRAM en Suspensión**: Habilitación de `NVreg_PreserveVideoMemoryAllocations=1` y `NVreg_TemporaryFilePath=/var/tmp` para salvaguardar el estado de la memoria de video durante ciclos de reposo.
- **Servicio `nvidia-max-performance.service`**: Activación automática en el arranque del script `gpu-performance.sh --boot` para garantizar PCIe en estado `D0`, Persistence Mode (`-pm 1`) y deshabilitación de `d3cold_allowed`.
- **Persistencia de Servicios de Usuario (Linger)**: Documentación y soporte para `loginctl enable-linger $USER`, impidiendo que los servidores locales (`gemma4`, `e4b`, `whisper`, `chatmanager`) se detengan al cerrar la sesión gráfica o bloquear el equipo.
- **Script de Despliegue de Servicios (`setup_enable_services.sh`)**: Automatización para copiar unidades systemd a `~/.config/systemd/user/`, recargar el demonio y habilitar los 4 servicios esenciales.

### Added - MCP Tools Ecosystem (146 Tools)
- **OSINT Suite (5 tools)**:
  - `osint_username`: Búsqueda en 3,300+ plataformas digitales (Maigret / Sherlock).
  - `osint_email`: Rastreo de cuentas asociadas a correo (Holehe).
  - `osint_domain`: Inteligencia DNS, subdominios y WHOIS.
  - `osint_ip`: Geolocalización, ASN y DNS inverso.
  - `osint_person`: Búsqueda de personas por nombre.
- **Búsqueda Web Avanzada (5 tools)**:
  - `search_google`: Búsqueda en Google con extracción de resúmenes de AI Mode.
  - `search_sports`: Marcadores y estadísticas deportivas en tiempo real.
  - `fetch_article`: Extracción de cuerpo de artículos con BeautifulSoup y lxml.
  - `search_with_content`: Búsqueda combinada con descarga automática del primer resultado.
  - `notify_contextual`: Disparo de notificación inteligente condicionado por decisión del LLM.
- **Asistente CLI MCP (`mcp_assistant.py`)**:
  - Cliente interactivo de terminal para dialogar con `llama-server` y ejecutar herramientas MCP en tiempo real.
  - Autodescubrimiento de servidores MCP desde `~/.config/mcp-servers.json`.
  - Soporte para comandos interactivos `/tools`, `/search`, `/clear`.
- **Sistema de Notificaciones Automáticas (`configs/notifications.conf`)**:
  - Notificaciones de escritorio automáticas para herramientas de escritura o tareas largas (>5s), con exclusión de herramientas de solo lectura y cooldown de 2s.

---

## [1.2.0] - 2026-08-30

### Added
- **Cloudflare R2 Object Storage**:
  - Módulo y CLI `r2` (`scripts/tools/r2_storage.py`) para interactuar con R2 (S3-compatible, $0 egress).
  - Herramientas MCP: `r2_upload`, `r2_list`, `r2_delete`, `r2_status`.
  - Configuración persistente y segura en `~/.config/ai-lab/r2.env`.
  - CDN público activo en `https://pub-1e0feaec3fa0410fa72dfccb31f05917.r2.dev`.
- **Visualización Multimedia Local en el Chat**:
  - Herramienta MCP `media_view` para renderizar imágenes, audios y videos locales directamente en `http://localhost:9090`.
  - Generación de Data-URIs Base64 en memoria para bypass de restricciones COEP (`Cross-Origin-Embedder-Policy: require-corp`) en la interfaz web de llama-server.
  - Endpoint de streaming local en ChatShare (`GET /api/v1/media?path=...`) con cabeceras `Cross-Origin-Resource-Policy: cross-origin`.
- **ChatShare Web Viewer Mejorado (`ai.castelancarpinteyro.com`)**:
  - Auto-subida de multimedia a Cloudflare R2 al exportar chats (`chat_export`).
  - Reproductores nativos HTML5 para audio (`.mp3`, `.wav`, `.ogg`, `.m4a`) y video (`.mp4`, `.webm`).
  - Visor modal Lightbox interactivo con zoom para imágenes.
  - Generación de códigos QR visuales en el chat para escaneo con cámara móvil.
  - Soporte para visualización detallada con bloques colapsables de razonamiento (`thinking`/`thought`), planning y tool calls, con switch a *Modo Minimal*.
  - Migración a puertos >= 9090 (puerto 9095) en VPS y entorno local para evitar colisiones.

### Fixed
- **Marked.js v12+**: Corrección de firmas de `renderer.link` y `renderer.image` mediante `extractMediaInfo()` para prevenir pantallas en blanco.
- **Plesk Nginx**: Limpieza de enlaces simbólicos corruptos `last_httpd.conf` en el VPS.

---

## [1.1.0] - 2026-08-30

### Added
- **ChatShare Backend Local-First**:
  - Servidor FastAPI en puerto 9095 con SQLite y migraciones Alembic (`~/.local/share/chatmanager/chats.db`).
  - Outbox Sync pattern para sincronización asíncrona con el VPS.
  - Generación de tokens de acceso con expiración automática.
- **Herramientas de Programación y Sistema**:
  - 16 herramientas GitHub (`gh_*`), 8 herramientas Git (`git_*`), 3 de Docker (`docker_*`), 3 de Cron (`cron_*`), 3 de Audio (`audio_*`), 4 de Red (`network_*`).
  - Herramientas de correo SMTP (`email_*`) y administración remota SSH (`ssh_*`).

---

## [1.0.0] - 2026-08-29

### Added
- Arquitectura multi-modelo local sobre hardware NVIDIA RTX 5060 Laptop (8GB VRAM).
- llama.cpp v0.3.0-dev (build b10688) con aceleración CUDA.
- Modelo principal Gemma 4 12B en GPU (puerto 9090, NGL=30, CTX=32K).
- Sub-agente Gemma 4 E4B en CPU (puerto 9091, NGL=0, CTX=8K).
- Servidor Whisper STT (puerto 9093) para reconocimiento de voz en tiempo real.
- Interfaz Open WebUI (puerto 9092) desplegada vía Docker Compose.
- Sistema de memoria persistente basado en SQLite (`~/.config/ai-memory.db`).
- Modos de Swap / Contexto configurables (`swap off`, `swap on`, `swap aggressive`).
- Gestión de servicios mediante `systemd --user`.

### Fixed
- **CUDA OOM**: Reducción de NGL de 40 a 30 en Gemma 4 12B para permitir 32K tokens de contexto estable dentro de los 8GB de VRAM.
- **GPU D3cold**: Creación del script `gpu-performance.sh` para reactivación de PCIe y forzado de modo rendimiento.
