# Problemas Encontrados y Soluciones

Registro integral de problemas técnicos, diagnósticos, causas raíz y soluciones implementadas en el ecosistema AI Lab.

---

## 1. GPU en Estado D3cold y Bloqueo PCIe

**Fecha:** 2026-08-27  
**Severidad:** Alta  
**Estado:** Resuelto  

### Problema
La tarjeta gráfica NVIDIA entra en estado de suspensión ultra profunda (`D3cold`) tras periodos de inactividad o arranque del sistema, provocando que `nvidia-smi` no responda y los servidores de inferencia fallen al inicializar el contexto de CUDA.

### Causa
Los sistemas de ahorro de energía dinámico de laptops activan `d3cold_allowed` y el runtime PM en el bus PCIe cuando no detectan llamadas activas al driver gráfico.

### Solución
Implementación del script `scripts/gpu/gpu-performance.sh` y el servicio `nvidia-max-performance.service`:
```bash
# Despertar forzado re-escaneando el bus PCI
echo 0 > /sys/bus/pci/devices/0000:01:00.0/remove
sleep 1
echo 1 > /sys/bus/pci/rescan
sleep 2

# Deshabilitar d3cold
echo 0 > /sys/bus/pci/devices/0000:01:00.0/power/d3cold_allowed

# Desactivar runtime PM
echo "on" > /sys/bus/pci/devices/0000:01:00.0/power/control

# Activar modo persistencia permanente
nvidia-smi -pm 1
```

---

## 2. CUDA Out of Memory (OOM) con Contexto Extendido (32K)

**Fecha:** 2026-08-28  
**Severidad:** Alta  
**Estado:** Resuelto  

### Problema
Al levantar el modelo principal Gemma 4 12B con `CTX=32768` y `NGL=40` (descarga total de capas a la GPU), el servidor sufre un crash inmediato por VRAM insuficiente.

### Causa
La GPU RTX 5060 Laptop cuenta con 8151 MiB de VRAM GDDR6. Con 40 capas descargadas más la memoria del KV Cache para 32,768 tokens, el requerimiento supera los 8.2 GB disponibles.

### Solución
Ajustar la descarga a `NGL=30` en `~/.config/gemma4-server.conf`:
- **Consumo de VRAM**: 6,141 MiB / 8,151 MiB (~2,010 MiB de margen libre).
- **Rendimiento**: ~16 tokens/segundo con estabilidad garantizada y soporte completo para 32K tokens de contexto.

---

## 3. MCP Server no carga tools por PYTHONPATH

**Fecha:** 2026-08-29  
**Severidad:** Media  
**Estado:** Resuelto  

### Problema
El servidor MCP no reconocía dependencias de scraping (`duckduckgo-search`, `bs4`, `whois`) al ser invocado desde `llama-server`.

### Causa
El entorno virtual de Python donde estaban instaladas las librerías no formaba parte del `sys.path` del intérprete por defecto.

### Solución
Inyección dinámica de rutas de paquetes en `scripts/tools/system_mcp_server.py`:
```python
venv_site = "/tmp/search-env/lib/python3.12/site-packages"
if os.path.exists(venv_site) and venv_site not in sys.path:
    sys.path.insert(0, venv_site)
```

---

## 4. Voice Input no disponible en la Interfaz Web

**Fecha:** 2026-08-29  
**Severidad:** Media  
**Estado:** Resuelto  

### Problema
Open WebUI no mostraba la opción de entrada de voz en tiempo real por micrófono.

### Causa
Falta de un endpoint compatible con la API de transcripción de audio de OpenAI.

### Solución
Creación del microservicio `scripts/tools/whisper_server.py` utilizando `faster-whisper` (modelo `base`, cuantización `int8`, ejecución en CPU) expuesto en el puerto `9093` con el endpoint `/v1/audio/transcriptions`.

---

## 5. Limitación en la Búsqueda Web

**Fecha:** 2026-08-29  
**Severidad:** Media  
**Estado:** Resuelto  

### Problema
Las herramientas de navegación iniciales solo abrían el navegador externo sin inyectar la información en el contexto del LLM.

### Causa
Ausencia de un scraper programático integrado.

### Solución
Integración de búsquedas directas sin dependencias externas pesadas:
- Búsqueda primaria: `search_google` con soporte para extracción de bloques AI Mode.
- Fallback y noticias: `search_news` y `web_search` vía DuckDuckGo.
- Extracción de artículos: `fetch_article` con BeautifulSoup y lxml.

---

## 6. Flag `--system-prompt` no soportado en llama.cpp

**Fecha:** 2026-08-29  
**Severidad:** Baja  
**Estado:** Resuelto  

### Problema
El binario compilado de `llama-server` rechazaba el argumento `--system-prompt`.

### Causa
Las versiones modernas de `llama.cpp` delegan el formateo de system prompt al motor de plantillas Jinja (`--jinja` y `--chat-template-file`).

### Solución
Configurar la plantilla oficial Jinja de Google Gemma 4 en `configs/systemd/gemma4-server.service` y almacenar las instrucciones en `configs/system-prompt.txt`.

---

## 7. Permisos de Docker Denegados

**Fecha:** 2026-08-29  
**Severidad:** Baja  
**Estado:** Resuelto  

### Problema
Al levantar contenedores de Open WebUI, Docker reportaba `Permission denied` al acceder al socket Unix.

### Solución
```bash
sudo usermod -aG docker $USER
newgrp docker
```

---

## 8. TDP de GPU Bloqueado en VBIOS

**Fecha:** 2026-08-27  
**Severidad:** Baja  
**Estado:** Documentado (Limitación de Hardware)  

### Problema
Intentos de modificar el límite de potencia (`nvidia-smi -pl`) arrojaban error.

### Causa
El fabricante de la placa base (ASUS) bloquea por firmware el power limit de la GPU RTX 5060 Laptop a un valor fijo de 55W (máximo configurable de 47-55W según modo térmico).

### Solución
Se ajustaron los perfiles del planificador y GPU offload para maximizar el throughput dentro del límite térmico de 55W.

---

## 9. Plesk Nginx: Error de Symlink 'last_httpd.conf'

**Fecha:** 2026-08-30  
**Severidad:** Alta  
**Estado:** Resuelto  

### Problema
Plesk fallaba al regenerar la configuración de Nginx para el subdominio `ai.castelancarpinteyro.com` indicando: `Refusing to create symlink '.../last_httpd.conf': file with the same name already exists`.

### Causa
Un enlace simbólico huérfano impedía la reconfiguración automática del proxy inverso.

### Solución
```bash
rm -f /var/www/vhosts/system/ai.castelancarpinteyro.com/conf/last_httpd.conf
plesk repair web ai.castelancarpinteyro.com -y
systemctl reload nginx
```

---

## 10. Marked.js v12+ Token Signature en Visor Web ChatShare

**Fecha:** 2026-08-30  
**Severidad:** Alta  
**Estado:** Resuelto  

### Problema
La interfaz web pública (`https://ai.castelancarpinteyro.com/view/...`) mostraba una pantalla en blanco debido a una excepción no capturada en JavaScript al renderizar enlaces o imágenes.

### Causa
`marked.js` v12+ modificó la firma de `renderer.link` y `renderer.image`, enviando un único objeto token `{ href, title, text }` en lugar de parámetros individuales.

### Solución
Se creó una función extractora universal `extractMediaInfo(tokenOrHref, title, text)` compatible con ambas versiones:
```javascript
function extractMediaInfo(tokenOrHref, title, text) {
    if (typeof tokenOrHref === 'object' && tokenOrHref !== null) {
        return {
            href: tokenOrHref.href || '',
            title: tokenOrHref.title || '',
            text: tokenOrHref.text || ''
        };
    }
    return { href: tokenOrHref || '', title: title || '', text: text || '' };
}
```

---

## 11. Restricción COEP en Interfaz Web de llama.cpp (:9090)

**Fecha:** 2026-08-30  
**Severidad:** Media  
**Estado:** Resuelto  

### Problema
Al intentar desplegar imágenes locales en el chat de `http://localhost:9090`, el navegador mostraba el error `"Image cannot be displayed (open link)"`.

### Causa
`llama-server` emite la cabecera `Cross-Origin-Embedder-Policy: require-corp`, bloqueando subrecursos HTTP provenientes de otros puertos locales sin cabecera CORP explícita.

### Solución
1. **Data-URI en Memoria (`media_view`)**: Convertir archivos menores a 8MB a `data:image/png;base64,...` directamente en la respuesta.
2. **Cabecera CORP en ChatShare (`GET /api/v1/media`)**: Añadir `Cross-Origin-Resource-Policy: cross-origin` para streaming de archivos grandes y video.

---

## 12. Bloqueo de GPU tras Suspensión en Plataformas AMD + NVIDIA (ASUS TUF)

**Fecha:** 2026-08-30  
**Severidad:** Crítica  
**Estado:** Resuelto  

### Problema
Al suspender el portátil o cerrar la tapa, al reanudar el sistema la GPU NVIDIA RTX 5060 quedaba en un estado zombi (`D3cold` irrecuperable), obligando a reiniciar el equipo por completo.

### Causa
El modo de suspensión S0ix (Modern Standby) en combinación con los perfiles predeterminados de `system76-power` y el driver propietario 580 causan pérdida del contexto de energía en el controlador PCIe de AMD.

### Solución
Configurar los parámetros del kernel en `/etc/modprobe.d/nvidia-graphics-drivers-sleep.conf` y `/etc/modprobe.d/system76-power.conf`:
```ini
options nvidia NVreg_EnableS0ixPowerManagement=0
options nvidia NVreg_PreserveVideoMemoryAllocations=1
options nvidia NVreg_TemporaryFilePath=/var/tmp
```
Al desactivar S0ix y activar la preservación de memoria de video en `/var/tmp`, el sistema utiliza suspensión S3 estándar donde la VRAM se guarda y restaura limpiamente.

---

## 13. Terminación de Servicios de Usuario tras Cerrar Sesión o Reposo

**Fecha:** 2026-08-30  
**Severidad:** Alta  
**Estado:** Resuelto  

### Problema
Los demonios `gemma4-server.service`, `e4b-server.service`, `whisper-server.service` y `chatmanager.service` se detenían al bloquear la pantalla o cerrar la sesión gráfica.

### Causa
Por defecto, `systemd` finaliza los procesos bajo `--user` cuando no hay una sesión interactiva abierta.

### Solución
Habilitar linger para el usuario:
```bash
sudo loginctl enable-linger darkseid
```
Esto garantiza que los servicios arranquen con el boot del sistema operativo y continúen ejecutándose ininterrumpidamente.

---

## 14. Saturación de Memoria y Pérdida de Hibernación en Contextos Agresivos (65K)

**Fecha:** 2026-08-30  
**Severidad:** Media  
**Estado:** Resuelto (Gestión por Perfiles)  

### Problema
Al utilizar el modo de swap agresivo (`CTX=65536`), el sistema operativo consumía hasta 28 GB de memoria combinada (RAM + ZRAM + NVMe Swap), impidiendo la hibernación (`systemctl hibernate`) por falta de espacio en la imagen de volcado.

### Causa
La imagen de hibernación requiere volcar toda la RAM activa al swap físico en disco (`/dev/dm-0`).

### Solución
Estructuración de tres modos de swap en `gemma4-ctl.sh`:
- **Modo Normal (`swap off`, CTX 16K)**: ~8GB RAM, hibernación completa garantizada.
- **Modo Swap (`swap on`, CTX 32K)**: ~14GB RAM, valor predeterminado recomendado.
- **Modo Agresivo (`swap aggressive`, CTX 64K)**: Para tareas analíticas masivas puntuales con advertencia explícita de hibernación no disponible.

---

## 15. Incompatibilidad de Modelos MoE de 26B/31B con Descarga a GPU (8GB VRAM)

**Fecha:** 2026-08-30  
**Severidad:** Baja  
**Estado:** Documentado  

### Problema
Los modelos Mixture of Experts (MoE) como Gemma 4 26B (128 expertos) no pueden ser descargados parcialmente a la GPU RTX 5060 de 8GB sin provocar caídas severas de velocidad o CUDA OOM.

### Causa
La arquitectura MoE requiere que las tablas de enrutamiento y múltiples expertos activos residan en memoria contigua, superando los 8GB de VRAM.

### Solución
- Mantener los modelos MoE en modo nativo CPU (`NGL=0`) con procesamiento multihilo AVX2/FMA.
- Reservar la aceleración GPU exclusivamente para el modelo denso de mayor eficiencia: **Gemma 4 12B (NGL=30)**.
