# AI Lab — Guía de Arquitectura, Rendimiento y Documentación Completa

Suite completa de inteligencia artificial local con aceleración GPU NVIDIA, arquitectura multi-modelo Gemma 4, servidor de transcripción Whisper, sistema de memoria persistente, plataforma de compartición de chats (ChatShare) y un ecosistema de **248 herramientas MCP**.

---

## 1. Hardware y Especificaciones del Entorno

| Componente | Especificación | Notas de Configuración |
|---|---|---|
| **GPU** | NVIDIA GeForce RTX 5060 Laptop (8GB GDDR6 VRAM) | Bus PCIe 0000:01:00.0, VBIOS TDP bloqueado a 55W |
| **Driver NVIDIA** | 580.173.02 (Open Kernel Module) | Persistence Mode activado (`-pm 1`) |
| **CUDA** | 13.0 (Driver Level) / Toolkit 12.0 | Soporte para llama.cpp con CUDA backend |
| **RAM** | 16 GB DDR5 (~14 GiB disponibles) | Asignada eficientemente entre GPU offload y CPU |
| **Swap & ZRAM** | 42 GB totales (14.9 GB ZRAM + 27.2 GB NVMe) | `vm.swappiness = 180`, compresión en RAM previa a disco |
| **llama.cpp** | v0.3.0-dev (Build b10688, commit c589f0ed1) | Servidores binarios compilados con soporte CUDA y Jinja |
| **Sistema Operativo** | Pop!_OS 24.04 LTS (Kernel Linux 6.9+) | Entorno optimizado para estabilidad de energía e IA |

---

## 2. Arquitectura del Sistema

El ecosistema opera mediante una topología distribuida de servicios locales coordinados en puertos dedicados (>= 9090):

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Puerto 9090 — Servidor Principal Gemma 4 12B (GPU Offload, NGL=30)         │
│  Web UI / API OpenAI: http://localhost:9090                                │
│  CTX=32768, 248 tools MCP modulares, Jinja Templating                      │
│  • Razonamiento profundo, planificación y orquestación                      │
│  • Visualización local multimedia sin internet (media_view / Base64)        │
│  • Delegación automática hacia sub-agente E4B                              │
│  • Orquestador: mcp_server.py (18 domain modules + 6 common utilities)     │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                    delegate_to_subagent / Fallback
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Puerto 9091 — Sub-Agente E4B (CPU Native, NGL=0)                           │
│  Web UI / API OpenAI: http://localhost:9091                                │
│  CTX=8192, ~42 tokens/seg                                                   │
│  • Control domótico Kasa, Spotify, consultas de sistema y OSINT             │
│  • Ejecución inmediata de baja latencia sin consumir VRAM de la GPU         │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Puerto 9092 — Open WebUI (Interfaz Web Avanzada)                           │
│  http://localhost:9092  (Desplegado vía Docker Compose)                    │
│  • Experiencia de chat completa, gestión de prompts y extensiones           │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Puerto 9093 — Whisper STT API Server (Speech-to-Text)                     │
│  http://localhost:9093/v1/audio/transcriptions                              │
│  • Modelo faster-whisper (base, CPU, int8) para asistente de voz           │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Puerto 9095 — ChatShare & Servidor Multimedia Local                        │
│  http://localhost:9095                                                      │
│  • Almacenamiento local de conversaciones (SQLite + Alembic)                │
│  • Servidor de streaming multimedia local con cabeceras CORS / CORP         │
│  • Outbox Sync Worker hacia VPS (https://ai.castelancarpinteyro.com)        │
│  • Generación de tokens seguros y códigos QR interactivos                   │
└─────────────────────────────────────────────────────────────────────────────┘
                                   │
                                   │ r2_upload / chat_export
                                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  Cloudflare R2 Object Storage (CDN Global, $0 Egress)                       │
│  https://pub-1e0feaec3fa0410fa72dfccb31f05917.r2.dev                       │
│  • Alojamiento de capturas, audios TTS y videos exportados                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Ajustes Críticos de Rendimiento, Suspensión y Energía

En portátiles con procesadores AMD y tarjetas gráficas dedicadas NVIDIA RTX serie 40/50 bajo Linux, la gestión de energía por defecto puede causar problemas graves: suspensión fallida, GPU colgada en bajo consumo (`D3cold`), pérdida de VRAM al reanudar y terminación de servicios en segundo plano. Se implementó una suite completa de optimizaciones a nivel de kernel, servicios y drivers:

### 3.1. Parámetros del Módulo del Kernel NVIDIA

Archivos de configuración:
- `/etc/modprobe.d/nvidia-performance.conf`
- `/etc/modprobe.d/nvidia-graphics-drivers-sleep.conf`
- `/etc/modprobe.d/system76-power.conf`

```ini
# Desactivación de S0ix (Modern Standby) en plataformas AMD/ASUS:
# El modo S0ix dejaba la GPU en estado D3cold irrecuperable al despertar
options nvidia NVreg_EnableS0ixPowerManagement=0

# Preservación de memoria de video durante ciclos de suspensión/reanudación:
options nvidia NVreg_PreserveVideoMemoryAllocations=1
options nvidia NVreg_TemporaryFilePath=/var/tmp

# Desactivación de Dynamic Power Management agresivo:
options nvidia NVreg_DynamicPowerManagement=0x00000000

# Activación de MSI (Message Signaled Interrupts) para menor latencia:
options nvidia NVreg_EnableMSI=1
```

### 3.2. Automatización del Despertar y Rendimiento PCIe (`gpu-performance.sh`)

Ubicación: `scripts/gpu/gpu-performance.sh` y servicio `nvidia-max-performance.service`.

El script gestiona el ciclo de vida del bus PCIe y la GPU:
1. **PCIe Rescan Fallback**: Si la GPU se encuentra en `D3cold` o `D3hot`, se remueve y re-escanea el bus PCI (`0000:01:00.0`) para forzar la transición a `D0`.
2. **D3cold Bypass**: Escribe `0` en `/sys/bus/pci/devices/0000:01:00.0/power/d3cold_allowed`.
3. **Runtime PM**: Fuerza `power/control = on`.
4. **Persistence Mode**: Activa `nvidia-smi -pm 1` para mantener los controladores cargados permanentemente en memoria y evitar el retardo de inicialización de CUDA.

```bash
# Comandos rápidos de GPU:
~/ai-lab/scripts/gpu/gpu-performance.sh --on      # Activar máximo rendimiento
~/ai-lab/scripts/gpu/gpu-performance.sh --status  # Consultar estado PCI y pstate
~/ai-lab/scripts/gpu/gpu-status.sh               # VRAM, temperatura y procesos
~/ai-lab/scripts/gpu/gpu-monitor.sh              # Monitor continuo en tiempo real
```

### 3.3. Jerarquía de Memoria, ZRAM y Modos de Swap

La memoria está configurada en dos niveles para soportar contextos de hasta 65K tokens sin bloquear el sistema:
1. **ZRAM (`/dev/zram0`, 14.9 GB, prioridad 1000)**: Compresión rápida en RAM (algoritmo zstd/lz4). Con `vm.swappiness = 180`, el kernel comprime páginas en RAM antes de escribir en el almacenamiento físico.
2. **Swap NVMe (`/dev/dm-0`, 27.2 GB, prioridad -1)**: Almacenamiento secundario para volcado masivo.

#### Modos de Contexto y Disponibilidad de Hibernación:

| Modo | CTX Size | Consumo Total RAM+Swap | Comportamiento con Hibernación |
|---|---|---|---|
| `swap off` | **16,384** | ~8 GB | **Hibernación completa disponible**: El estado entra perfectamente en la partición swap física. |
| `swap on` (Default) | **32,768** | ~14 GB | **Hibernación disponible con límite**: Requiere espacio libre adecuado en la partición swap. |
| `swap aggressive` | **65,536** | ~28 GB | **Sin hibernación**: La memoria utilizada supera el espacio seguro de volcado. |

```bash
# Cambiar modo de swap/contexto:
~/ai-lab/scripts/llama/gemma4-ctl.sh swap off
~/ai-lab/scripts/llama/gemma4-ctl.sh swap on
~/ai-lab/scripts/llama/gemma4-ctl.sh swap aggressive
```

### 3.4. Preservación de Procesos de Usuario y Linger (`systemd --user`)

Para que los servidores locales (`gemma4-server`, `e4b-server`, `whisper-server`, `chatmanager`) no se detengan al bloquear la pantalla, cerrar la sesión gráfica o entrar en reposo:
```bash
# Habilitar persistencia de procesos sin sesión gráfica:
sudo loginctl enable-linger $USER

# Despliegue y habilitación automática de servicios:
~/ai-lab/scripts/setup_enable_services.sh
```

---

## 4. Catálogo Completo de Herramientas MCP (248 Tools Modulares)

El orquestador `scripts/tools/mcp_server.py` expone **248 herramientas** estructuradas según el estándar Model Context Protocol (JSON-RPC 2.0), distribuidas en 21 domain modules con auto-discovery.

### 4.1. Visualización Multimedia Local (1)
- `media_view`: Genera Data-URIs Base64 en memoria (archivos <8MB) o enlaces de streaming CORS desde `http://localhost:9095/api/v1/media` para renderizar imágenes, audios y videos directamente en la interfaz web de `llama-server` (:9090) sorteando restricciones de COEP (`Cross-Origin-Embedder-Policy: require-corp`).

### 4.2. Cloudflare R2 Object Storage (4)
- `r2_upload`: Sube cualquier archivo local (imágenes, audios TTS, grabaciones Whisper, videos) a Cloudflare R2 con enlace público CDN permanente ($0 egress).
- `r2_list`: Lista objetos almacenados en el bucket `ai-lab`.
- `r2_delete`: Elimina archivos del almacenamiento R2.
- `r2_status`: Diagnostica y prueba la conexión contra las APIs S3 de Cloudflare.

### 4.3. ChatShare & Compartir Conversaciones (4)
- `chat_export`: Exporta la conversación completa (incluyendo mensajes íntegros, razonamiento/planning, llamadas a tools y multimedia subida a R2) a `ai.castelancarpinteyro.com` con código QR visual interactivo.
- `chat_share`: Genera un enlace público con token de acceso y expiración personalizable para un chat existente.
- `chat_list_shared`: Lista los chats locales registrados en la base de datos de ChatShare.
- `chat_get_shared`: Recupera el contenido íntegro estructurado de un chat por su UUID.

### 4.4. Smart Home Kasa (2)
- `kasa_set_plug_state`: Enciende o apaga enchufes inteligentes TP-Link Kasa por nombre o IP.
- `kasa_get_plugs_status`: Consulta el estado actual (on/off, consumo, potencia) de los enchufes de la red.

### 4.5. Gestión de Sistema y Archivos (14)
- `list_directory`: Lista directorios con tamaños, permisos y metadatos.
- `file_info`: Información detallada (MIME, inodos, hashes, fechas) de un archivo.
- `search_files`: Búsqueda recursiva por patrones glob y regex.
- `read_file`: Lectura de archivos con paginación de líneas.
- `write_file`: Creación o modificación de archivos locales.
- `run_command`: Ejecución controlada de comandos en terminal Linux con timeouts.
- `get_system_info`: Métricas globales de CPU, RAM, Swap, Uptime y Kernel.
- `get_gpu_status`: Estado NVIDIA: temperatura, VRAM en uso/libre, potencia y P-State.
- `screenshot`: Captura de pantalla completa o de ventanas activas.
- `clipboard`: Lectura y escritura en el portapapeles del sistema (xclip/wl-clipboard).
- `brightness`: Lectura y ajuste del brillo de pantalla.
- `weather`: Información meteorológica actual y pronóstico local vía wttr.in.
- `timer`: Configuración de temporizadores y alarmas del sistema.
- `notes`: Gestión y categorización de notas rápidas en `~/.notes/`.

### 4.6. Navegación Web y Ejecución de Código (3)
- `web_search`: Búsqueda rápida en la web vía DuckDuckGo.
- `open_url`: Abre enlaces en el navegador predeterminado del usuario.
- `run_python_script`: Ejecuta scripts Python aislados con captura de stdout/stderr.

### 4.7. Multimedia y Notificaciones (2)
- `media_control`: Control de reproducción global (Play/Pause, Next, Prev, Volume) vía MPRIS2.
- `send_notification`: Notificación de escritorio avanzada (soporta urgencia, iconos temáticos, timeout y modo transitorio).

### 4.8. Spotify Avanzado (12)
- `spotify_search`: Búsqueda de pistas, álbumes y artistas.
- `spotify_now`: Consulta de la pista en reproducción actual.
- `spotify_play` / `spotify_pause`: Control de reproducción.
- `spotify_next` / `spotify_previous`: Navegación de pistas.
- `spotify_volume`: Ajuste preciso de volumen (0-100%).
- `spotify_playlists`: Listado de playlists del usuario.
- `spotify_launch`: Lanzamiento de la aplicación Spotify.
- `spotify_play_track`: Búsqueda y reproducción directa de una canción.
- `spotify_play_artist`: Reproducción aleatoria o destacada de un artista.
- `spotify_play_playlist`: Reproducción de una lista específica.

### 4.9. Memoria Persistente SQLite (5)
- `memory_save`: Almacena un recuerdo estructurado (`note`, `fact`, `preference`, `context`, `task`).
- `memory_search`: Búsqueda contextual por similitud o tags.
- `memory_context`: Recupera los datos de memoria relevantes para la conversación activa.
- `memory_list`: Lista los recuerdos más recientes.
- `memory_delete`: Elimina un recuerdo por ID.

### 4.10. Delegación de Tareas (1)
- `delegate_to_subagent`: Redirige tareas de baja latencia o herramientas específicas al sub-agente E4B en puerto 9091.

### 4.11. Ecosistema GitHub (16)
- `gh_repos_list`, `gh_repo_info`, `gh_repo_create`: Gestión de repositorios remotos.
- `gh_issues_list`, `gh_issue_create`: Consulta y creación de issues.
- `gh_pr_list`, `gh_pr_create`, `gh_pr_merge`: Ciclo de vida de Pull Requests.
- `gh_actions_list`, `gh_actions_runs`: Monitoreo de flujos CI/CD en GitHub Actions.
- `gh_release_list`: Consulta de releases y artefactos.
- `gh_gist_list`, `gh_gist_create`: Gestión de snippets/gists.
- `gh_search_repos`, `gh_search_code`: Búsqueda de repositorios y código en GitHub.

### 4.12. Control Git Local (8)
- `git_status`: Estado del árbol de trabajo.
- `git_log`: Historial de commits con formato configurable.
- `git_diff`: Visualización de diferencias unstaged/staged.
- `git_branches`: Listado y estado de ramas locales y remotas.
- `git_commit`: Creación de commits con mensajes formateados.
- `git_push` / `git_pull`: Sincronización con remotos.
- `git_clone`: Clonado de repositorios.

### 4.13. Análisis de Código y Proyectos (5)
- `code_analyze`: Métricas de complejidad y calidad estática.
- `code_count_lines`: Conteo de líneas de código (SLOC) por lenguaje.
- `code_search_pattern`: Búsqueda de patrones estructurales y expresiones regulares.
- `project_dependencies`: Análisis de dependencias (`package.json`, `requirements.txt`, `Cargo.toml`, etc.).
- `project_structure`: Generación de mapas de árbol y arquitectura de directorios.

### 4.14. Docker (3)
- `docker_ps`: Contenedores en ejecución y estados.
- `docker_logs`: Extracción de logs de contenedores.
- `docker_images`: Listado de imágenes disponibles localmente.

### 4.15. Ciclo de Vida del Sistema y Utilidades de Archivos (4)
- `system_shutdown`: Control de apagado, reinicio, suspensión e hibernación controlada.
- `file_compress`: Compresión en formatos `.zip`, `.tar.gz`, `.tar.bz2`.
- `file_extract`: Descompresión automática de paquetes.
- `file_permissions`: Modificación de permisos POSIX (chmod/chown).

### 4.16. Redes y Conectividad (4)
- `network_ping`: Comprobación de latencia y disponibilidad ICMP.
- `network_ports`: Escaneo de puertos locales y sockets en escucha (`ss`/`netstat`).
- `network_speed`: Prueba de velocidad de descarga/subida de conexión a internet.
- `network_info`: Interfaces de red, IPs locales, gateways y DNS activos.

### 4.17. Gestión de Procesos (3)
- `process_list`: Listado de procesos con uso de CPU y memoria.
- `process_kill`: Envío de señales (`SIGTERM`, `SIGKILL`) a procesos por PID.
- `process_search`: Búsqueda de procesos por nombre o línea de comandos.

### 4.18. Tareas Programadas Cron (3)
- `cron_list`: Consulta de crontab del usuario.
- `cron_add`: Programación de nuevas tareas periódicas.
- `cron_delete`: Eliminación de entradas en el cron.

### 4.19. Enrutamiento de Audio (3)
- `audio_list_devices`: Listado de fuentes y sumideros PulseAudio/PipeWire.
- `audio_set_source`: Selección de dispositivo de salida de audio predeterminado.
- `audio_set_source_input`: Enrutamiento dinámico de streams de aplicaciones.

### 4.20. Monitoreo y Rendimiento de Disco (4)
- `monitor_realtime`: Métricas en vivo de CPU, memoria y E/S.
- `monitor_top_processes`: Procesos ordenados por consumo de recursos.
- `disk_usage`: Espacio ocupado y disponible por punto de montaje.
- `disk_io`: Estadísticas de lectura/escritura y saturación de disco.

### 4.21. Correo Electrónico SMTP/IMAP (11)
- `email_send`: Envío de correos electrónicos vía SMTP con smtplib directo (texto plano y HTML, adjuntos).
- `email_list`: Listar correos de una carpeta (INBOX, etc.) con paginación.
- `email_read`: Leer un correo completo por ID con headers y cuerpo.
- `email_search`: Buscar correos por asunto, remitente o contenido.
- `email_folders`: Listar carpetas disponibles en el servidor IMAP.
- `email_mark_read`: Marcar un correo como leído.
- `email_delete`: Eliminar un correo por ID.
- `email_configure`: Almacenamiento seguro de credenciales SMTP/IMAP en `~/.msmtprc`.
- `email_test`: Verificación de handshake y autenticación SMTP.
- `email_discover_settings`: Autodescubrimiento de servidores SMTP/IMAP por registros DNS MX.
- `email_setup_wizard`: Asistente interactivo de configuración y prueba de correo.

### 4.22. Administración Remota SSH (8)
- `ssh_connect`: Ejecución segura de comandos remotos vía SSH.
- `ssh_copy`: Subida de archivos mediante SCP/SFTP.
- `ssh_fetch`: Descarga de archivos remotos a la máquina local.
- `ssh_sync`: Sincronización bidireccional de directorios con `rsync`.
- `ssh_tunnel`: Creación de túneles persistentes con `autossh`.
- `ssh_list_hosts`: Lectura de hosts configurados en `~/.ssh/config`.
- `ssh_add_host`: Adición de nuevos servidores al archivo de configuración SSH.
- `ssh_status`: Verificación de conectividad y estado de servidores remotos.

### 4.23. Comunicación y Formateo (5)
- `send_notification`: Notificación de escritorio parametrizada.
- `notify_contextual`: Disparo de notificación inteligente condicionado por decisión del LLM.
- `format_whatsapp`: Formateo de texto enriquecido adaptado para WhatsApp (listas, negritas, emojis).
- `whatsapp_link`: Generación de enlaces de contacto directo `https://wa.me/` con mensaje prellenado.
- `format_email`: Generador de plantillas de correo multi-parte.

### 4.24. Búsqueda Web Avanzada e Inteligencia (11)
- `browse_web`: Descarga de contenido de URLs (HTML, JSON o texto limpio).
- `http_request`: Cliente HTTP genérico para peticiones REST (GET, POST, PUT, DELETE, PATCH).
- `search_google`: Búsqueda en Google con extracción de resúmenes AI Mode.
- `search_news`: Búsqueda de noticias de última hora en DuckDuckGo News.
- `search_docs`: Búsqueda especializada en portales de documentación técnica.
- `search_sports`: Marcadores y resultados deportivos en tiempo real.
- `fetch_article`: Extracción de cuerpo de artículos web utilizando BeautifulSoup y lxml.
- `search_with_content`: Búsqueda web combinada con descarga automática del contenido del primer resultado relevante.
- `dns_lookup`: Consultas DNS avanzadas (registros A, AAAA, MX, TXT, NS, CNAME).
- `ssl_check`: Inspección de certificados SSL/TLS, validez y fechas de expiración.
- `whois_lookup`: Consulta de datos de registro WHOIS para nombres de dominio.

### 4.25. Bases de Datos Locales SQLite (2)
- `sql_query`: Ejecución de consultas SQL directas sobre bases de datos SQLite locales.
- `backup_database`: Creación de respaldos consistentes de bases de datos SQLite.

### 4.26. Procesamiento y Conversión de Datos (7)
- `csv_to_json`: Conversión de archivos tabulares CSV a formato JSON.
- `json_to_csv`: Conversión de estructuras JSON a CSV estructurado.
- `convert_file`: Conversor universal multi-formato (CSV, JSON, XML, YAML, Markdown).
- `extract_pdf`: Extracción de texto y metadatos de documentos PDF.
- `generate_csv`: Creación de archivos CSV a partir de matrices de datos.
- `data_analysis`: Cálculo de estadísticas descriptivas (medias, medianas, varianzas, correlaciones).

### 4.27. Seguridad y Auditoría del Sistema (4)
- `log_analysis`: Análisis de logs de `journalctl`, `/var/log/syslog` y servidores web.
- `generate_report`: Generación automática de informes ejecutivos en formato Markdown.
- `security_audit`: Auditoría de puertos abiertos, permisos de archivos sensibles y configuraciones de red.
- `secret_detection`: Escaneo de código fuente para detectar claves API, tokens y secretos expuestos.

### 4.28. Planificación y Tareas (1)
- `plan_tasks`: Generación estructurada de planes de acción paso a paso.

### 4.29. Inteligencia de Fuentes Abiertas — OSINT (5)
- `osint_username`: Rastreo de nombres de usuario en más de 3,300 plataformas digitales (Maigret / Sherlock).
- `osint_email`: Identificación de cuentas vinculadas a correos electrónicos mediante Holehe (100+ servicios).
- `osint_domain`: Inteligencia integral de dominios (DNS, subdominios, certificados y registros).
- `osint_ip`: Geolocalización, ASN, proveedor de servicios y resolución DNS inversa de direcciones IP.
- `osint_person`: Búsqueda correlacionada de personas por nombre completo en directorios públicos.

### 4.30. Auditoría, Trazabilidad y Observabilidad (2)
- `audit_get_metrics`: Consulta métricas agregadas de rendimiento de herramientas (latencia media/máx, tasa de éxito, tokens estimados y consumo de VRAM/temperatura de GPU) en ventanas de tiempo personalizables.
- `audit_list_traces`: Consulta y filtra las trazas de ejecución más recientes en la base de datos de auditoría local (`~/.local/share/ai-lab/audit_traces.db`) para auto-diagnóstico y depuración.

### 4.31. Flujos de Trabajo Declarativos y Automatización DAG (3)
- `workflow_list`: Lista los pipelines de automatización disponibles registrados en `configs/workflows/` (`daily_briefing`, `system_health_audit`, etc.).
- `workflow_run`: Ejecuta un pipeline DAG multi-paso con resolución de dependencias, interpolación de variables e historial en base de datos SQLite.
- `workflow_status`: Consulta el progreso, métricas de latencia por paso y resultados de una ejecución histórica por su ID.

### 4.32. Memoria Vectorial Semántica y RAG Local (4)
- `vector_search`: Recuperación semántica por similitud coseno sobre fragmentos de código, notas y documentación local indexada.
- `vector_index_path`: Indexación bajo demanda de directorios o archivos en la base de datos vectorial local (`~/.local/share/ai-lab/vectors/vector_store.db`).
- `vector_remember`: Almacenamiento de recuerdos episódicos y preferencias del usuario en memoria semántica permanente.
- `vector_stats`: Consulta el número total de fragmentos indexados, colecciones y tamaño de la base vectorial.

### 4.33. Navegación Web Headless y Sincronización de Identidades Brave (12)
- `browser_navigate`: Navegación web con Brave Browser headless mediante Chrome DevTools Protocol (CDP nativo).
- `browser_extract_text`: Extracción de contenido de texto formateado por selector CSS o documento completo.
- `browser_extract_markdown`: Modo lectura optimizado: convierte el contenido principal a Markdown estructurado eliminando publicidad y elementos distractores.
- `browser_click`: Clic en enlaces, botones o elementos interactivos de páginas web complejas/SPAs.
- `browser_type`: Inyección de texto en inputs, selectores o envío de formularios.
- `browser_screenshot`: Captura visual de pantalla (scroll completo o parcial) almacenada para `media_view`.
- `browser_print_pdf`: Exporta e imprime cualquier página web a documento PDF de alta fidelidad.
- `browser_get_links`: Extracción exhaustiva de hipervínculos y URLs de la página web activa.
- `browser_list_tabs`: Lista y monitorea las pestañas activas en el navegador headless.
- `browser_sync_brave_profile`: Sincronización segura de cookies SQLite (`Network/Cookies`), Local Storage y sesiones autenticadas desde el navegador personal Brave (`~/.config/BraveSoftware/Brave-Browser/Default`).
- `browser_clear_session`: Limpieza de cookies y caché para navegación anónima en modo incógnito.
- `browser_status`: Diagnóstico del estado del proceso headless, página activa y puerto CDP.

### 4.34. Asistencia Visual de Escritorio Multi-Monitor y Contexto Activo (4)
- `desktop_context_explain`: Inspección contextual omnipotente: analiza qué está haciendo el usuario en pantalla, identifica botones/opciones y sugiere acciones proactivas con apoyo de documentación local (RAG).
- `desktop_list_monitors`: Detección y lista de monitores físicos conectados (`xrandr`), resoluciones y geometrías.
- `desktop_list_windows`: Detección y lista de ventanas abiertas, aplicaciones, PIDs y estado de foco.
- `desktop_capture_region`: Captura de ventana activa, monitor concreto o región rectangular personalizada guardada para `media_view`.

### 4.35. Voz Bidireccional Full-Duplex, Diagnóstico de Audio y Perfiles (11)
- `voice_speak`: Síntesis de voz y streaming en tiempo real vía PipeWire con soporte para interrupción inmediata (Barge-In).
- `voice_listen`: Captura de audio de micrófono con Voice Activity Detection (VAD) inteligente y transcripción automática por Whisper (:9093).
- `voice_status`: Monitoreo y diagnóstico de los subsistemas de audio, motores TTS (Piper / spd-say), Whisper STT y micrófono.
- `voice_set_profile`: Personalización en caliente de perfiles de voz, idioma, acento, velocidad de habla y tono.
- `voice_list_profiles`: Catálogo de perfiles de voz disponibles (Español México, Castellano España, Inglés US/UK, Rápido).
- `voice_conversational_turn`: Ciclo continuo conversacional manos libres por voz (escucha VAD -> razonamiento LLM -> síntesis con Barge-In).
- `audio_check_volume`: Diagnóstico de volumen del sistema y silenciador (Mute) con notificaciones de alerta si no es audible.
- `audio_set_volume`: Ajuste directo del volumen y desmutear bocinas del sistema.
- `vision_analyze_image`: Inferencia visual multimodal mediante la API de Gemma 4 / llama.cpp con fallback estructurado a OCR.
- `vision_inspect_screen`: Captura de pantalla de escritorio en vivo e inspección visual inteligente.
- `vision_ocr`: Extracción de texto y análisis de estructura visual usando Tesseract OCR local.

### 4.36. Fútbol y Deportes — API BSD (20)
- `football_search_matches`: Búsqueda de partidos por fecha, liga o equipo.
- `football_get_match`: Detalle completo de un partido (goles, eventos, estadísticas).
- `football_live_scores`: Marcadores en vivo en tiempo real.
- `football_get_match_h2h`: Historial de enfrentamientos directos entre dos equipos.
- `football_get_match_lineups`: Alineaciones titulares y suplentes.
- `football_get_match_shotmap`: Mapa de tiros de un partido.
- `football_get_match_incidents`: Todos los eventos (goles, tarjetas, sustituciones).
- `football_search_teams`: Búsqueda de equipos por nombre.
- `football_get_team`: Información completa de un equipo (plantilla, próximo partido).
- `football_get_team_fixtures`: Calendario de próximos partidos de un equipo.
- `football_search_players`: Búsqueda de jugadores por nombre.
- `football_get_player`: Información completa de un jugador (posición, edad, equipo).
- `football_get_player_stats`: Estadísticas detalladas (goles, asistencias, minutos).
- `football_get_standings`: Clasificación de una liga/torneo.
- `football_list_leagues`: Catálogo de ligas disponibles.
- `football_list_seasons`: Temporadas disponibles por liga.
- `football_compare_odds`: Comparación de cuotas de casas de apuestas.
- `football_get_predictions`: Pronósticos y predicciones de IA.
- `football_list_venues`: Estadios disponibles.
- `football_list_referees`: Árbitros registrados.

---

## 5. Sistema de Notificaciones Automáticas (`configs/notifications.conf`)

El servidor MCP incluye un despachador de notificaciones de escritorio que alerta automáticamente al usuario tras la ejecución de herramientas de acción (creación, edición, borrado, subidas a red), omitiendo inteligentemente herramientas de solo lectura para evitar saturación:

```ini
[notify]
enabled = true
cooldown = 2
on_error = true
on_execute = true
on_long_task = true
long_task_seconds = 5
```

---

## 6. Asistente de Terminal MCP (`mcp_assistant.py`)

Para interactuar directamente con el ecosistema desde la línea de comandos sin abrir la interfaz web, el script `scripts/mcp_assistant.py` proporciona un cliente interactivo completo conectado a `llama-server` y al protocolo MCP:

```bash
# Modo interactivo:
python3 ~/ai-lab/scripts/mcp_assistant.py

# Modo prompt directo:
python3 ~/ai-lab/scripts/mcp_assistant.py "Monitorea el estado de la GPU y toma una captura de pantalla"

# Comandos internos en modo interactivo:
# /tools    -> Listar todas las herramientas cargadas
# /search X -> Buscar herramientas por palabra clave
# /clear    -> Limpiar historial de conversación
```

---

## 7. Plataforma ChatShare y Visor Web

ChatShare permite registrar, almacenar con control de versiones y compartir públicamente conversaciones completas generadas en el laboratorio:

- **Almacenamiento Local-First**: Base de datos SQLite gestionada con migraciones Alembic en `~/.local/share/chatmanager/chats.db`.
- **Sincronización Outbox con VPS**: Worker en segundo plano que sincroniza conversaciones hacia `https://ai.castelancarpinteyro.com` cada 30 segundos.
- **Visor Web Enriquecido**:
  - Renderizado completo de Markdown mediante `marked.js` adaptado a la firma de tokens v12+.
  - Bloques colapsables de razonamiento profundo (`thinking` / `thought`) y llamadas a herramientas (`tool_calls`), con selector a **Modo Minimal**.
  - Reproductores nativos HTML5 para archivos de audio y video.
  - Visor modal Lightbox interactivo para imágenes.
  - Generación de código QR visual para escaneo móvil inmediato.

---

## 8. Guía de Servicios y Gestión

```bash
# Iniciar todos los servicios de usuario:
systemctl --user start gemma4-server.service e4b-server.service whisper-server.service chatmanager.service

# Comprobar estado de los servicios:
systemctl --user status gemma4-server.service e4b-server.service whisper-server.service chatmanager.service

# Visualizar logs en tiempo real:
journalctl --user -u gemma4-server.service -f
journalctl --user -u chatmanager.service -f
```

---

## 9. Índice de Documentación Detallada

- 🗺️ [**Roadmap y Fases de Evolución (`docs/roadmap/ROADMAP.md`)**](file:///home/darkseid/ai-lab/docs/roadmap/ROADMAP.md): Plan de desarrollo en 5 fases (Autonomía, Eventos, Vector RAG, Playwright y Full-Duplex Voice).
- 📘 [**Problemas Encontrados y Diagnóstico (`docs/problems/PROBLEMS.md`)**](file:///home/darkseid/ai-lab/docs/problems/PROBLEMS.md): Registro de los 15 problemas críticos y su resolución (GPU D3cold, VRAM OOM, COEP bypass, suspension S0ix, etc.).
- 🛠️ [**Soluciones de Arquitectura e Ingeniería (`docs/solutions/SOLUTIONS.md`)**](file:///home/darkseid/ai-lab/docs/solutions/SOLUTIONS.md): Patrones de diseño técnico (jerarquía de memoria ZRAM/Swap, persistencia PCIe, topología multi-agente, Cloudflare R2 y ChatShare outbox).
- 📜 [**Historial de Versiones (`docs/changelog/CHANGELOG.md`)**](file:///home/darkseid/ai-lab/docs/changelog/CHANGELOG.md): Detalle cronológico de cambios de v1.0.0 a v1.8.0.

