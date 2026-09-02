# AI Lab — Guía de Soluciones de Ingeniería y Arquitectura

Este documento consolida las soluciones técnicas, patrones de diseño y decisiones de arquitectura implementadas en el ecosistema **AI Lab** para garantizar alta disponibilidad, rendimiento óptimo sobre hardware restringido (8GB VRAM), visualización multimedia y compartición distribuida.

---

## 1. Gestión de Energía y Ciclo de Vida GPU (NVIDIA RTX 5060 + AMD)

### Desafío
En portátiles híbridos AMD + NVIDIA con drivers modernos (580.x), el modo Modern Standby (S0ix) provoca que la GPU entre en un estado D3cold irreversible tras suspender o cerrar la tapa, requiriendo un reinicio forzado del sistema.

### Solución Implementada
1. **Desactivación de S0ix y Preservación de VRAM en Kernel**:
   Configuración en `/etc/modprobe.d/nvidia-graphics-drivers-sleep.conf` y `/etc/modprobe.d/system76-power.conf`:
   ```ini
   options nvidia NVreg_EnableS0ixPowerManagement=0
   options nvidia NVreg_PreserveVideoMemoryAllocations=1
   options nvidia NVreg_TemporaryFilePath=/var/tmp
   options nvidia NVreg_DynamicPowerManagement=0x00000000
   options nvidia NVreg_EnableMSI=1
   ```
2. **Reactivación Automática y Rescan PCIe (`gpu-performance.sh`)**:
   - Forzado de estado de energía a `D0` mediante re-escaneo del bus PCIe `0000:01:00.0`.
   - Inyección de `0` en `/sys/bus/pci/devices/0000:01:00.0/power/d3cold_allowed`.
   - Activación de *Persistence Mode* (`nvidia-smi -pm 1`) permanente mediante el servicio systemd `nvidia-max-performance.service`.

---

## 2. Jerarquía de Memoria y Gestión de Contexto Extendido

### Desafío
Ejecutar modelos de 12B parámetros con contextos de 32K a 65K tokens en un equipo con 16 GB de RAM física y 8 GB de VRAM sin provocar CUDA OOM ni congelar el sistema operativo.

### Solución Implementada
1. **Configuración de Memoria en Dos Niveles**:
   - **ZRAM (`/dev/zram0`, 14.9 GB, Prioridad 1000)**: Compresión ultrarrápida en RAM mediante algoritmo zstd/lz4.
   - **Swap NVMe (`/dev/dm-0`, 27.2 GB, Prioridad -1)**: Respaldo secundario en disco de alta velocidad.
   - Parámetro de kernel: `vm.swappiness = 180` para priorizar compresión en RAM antes de escribir en disco.
2. **Descarga de Capas Optimizada (`NGL=30`)**:
   - Al asignar 30 capas a la GPU RTX 5060, el modelo consume ~6,141 MiB de VRAM, dejando ~2,010 MiB de colchón para el KV Cache de 32K tokens.
3. **Perfiles Dinámicos de Contexto y Swap (`gemma4-ctl.sh`)**:
   - `swap off` (CTX 16K, ~8GB RAM): Garantiza soporte completo de hibernación en disco (`systemctl hibernate`).
   - `swap on` (CTX 32K, ~14GB RAM): Configuración estándar para trabajo general y razonamiento complejo.
   - `swap aggressive` (CTX 64K, ~28GB RAM): Para análisis masivo de documentos y código extenso.

---

## 3. Topología de Inferencia Multi-Modelo y Delegación

### Desafío
Evitar la saturación de la GPU al ejecutar simultáneamente razonamiento complejo y herramientas rápidas de sistema o domótica.

### Solución Implementada
Arquitectura de doble agente coordinado:
- **Agente Principal (Puerto 9090)**: `Gemma 4 12B` en GPU (NGL=30, CTX=32K). Encargado de razonamiento, planificación, código y orquestación.
- **Sub-Agente Rápido (Puerto 9091)**: `Gemma 4 E4B` en CPU (NGL=0, CTX=8K, ~42 tokens/seg). Atiende herramientas de baja latencia (Spotify, Kasa, OSINT, status) invocadas mediante `delegate_to_subagent`.

---

## 4. Visualización Multimedia en Web UI y Bypass de COEP

### Desafío
La interfaz web de `llama-server` emite la cabecera `Cross-Origin-Embedder-Policy: require-corp`, bloqueando cualquier imagen o recurso servido desde otros puertos locales (`http://localhost:9095`), mostrando el error `"Image cannot be displayed"`.

### Solución Implementada
1. **Data-URIs Base64 en Memoria (`media_view`)**:
   Para archivos de imagen y multimedia < 8MB, la herramienta codifica el archivo directamente en Base64 (`data:image/png;base64,...`). La UI de Svelte de llama.cpp renderiza Data-URIs de forma nativa sin generar peticiones de red cruzadas.
2. **Cabecera CORP en Servidor Local ChatShare**:
   El endpoint `/api/v1/media` en el puerto 9095 incorpora la cabecera HTTP:
   ```http
   Cross-Origin-Resource-Policy: cross-origin
   Access-Control-Allow-Origin: *
   ```
   Permitiendo streaming de video y audio pesado de forma fluida.

---

## 5. Distribución Global CDN con Cloudflare R2 y ChatShare Sync

### Desafío
Compartir conversaciones extensas con capturas, audio TTS y videos sin sobrecargar el ancho de banda del servidor VPS ni incurrir en costes de salida de datos (egress).

### Solución Implementada
1. **Almacenamiento CDN R2 ($0 Egress)**:
   - Integración nativa con Cloudflare R2 S3 API mediante `scripts/tools/r2_storage.py` y tools `r2_*`.
   - Las imágenes y audios se distribuyen globalmente desde `https://pub-1e0feaec3fa0410fa72dfccb31f05917.r2.dev`.
2. **Patrón Outbox y Sincronización Asíncrona**:
   - Base de datos local SQLite con migraciones Alembic (`~/.local/share/chatmanager/chats.db`).
   - Worker en segundo plano sincroniza chats cada 30 segundos con el VPS (`ai.castelancarpinteyro.com`).
3. **Visor Web Enriquecido**:
   - Renderizado con `marked.js` adaptado a la firma v12+ mediante la función universal `extractMediaInfo()`.
   - Visor Lightbox con zoom para capturas de pantalla.
   - Generación de código QR visual para lectura móvil instantánea.

---

## 6. Ecosistema Extensible de Herramientas MCP (146 Tools)

### Desafío
Proveer a la IA de capacidades completas de administración de sistema, OSINT, scraping web, domótica, bases de datos y DevOps sin ralentizar el tiempo de respuesta.

### Solución Implementada
- Servidor central `scripts/tools/system_mcp_server.py` implementando el estándar **Model Context Protocol (JSON-RPC 2.0)**.
- Despacho modular de 146 herramientas en 29 categorías funcionales.
- Notificaciones automáticas de escritorio parametrizables (`configs/notifications.conf`) con cooldown para evitar spam.
- Cliente CLI interactivo `scripts/mcp_assistant.py` para operar la IA desde terminal con auto-tool calling.

---

## 7. Alta Disponibilidad de Servicios de Usuario (Linger)

### Desafío
Los demonios de usuario bajo `systemd --user` eran finalizados por el sistema al bloquear la sesión o cerrar sesión gráfica.

### Solución Implementada
- Activación de persistencia de usuario mediante `sudo loginctl enable-linger $USER`.
- Despliegue automatizado de servicios mediante `scripts/setup_enable_services.sh` para:
  - `gemma4-server.service` (Puerto 9090)
  - `e4b-server.service` (Puerto 9091)
  - `whisper-server.service` (Puerto 9093)
  - `chatmanager.service` (Puerto 9095)
