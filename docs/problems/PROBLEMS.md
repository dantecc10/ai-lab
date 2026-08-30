# Problemas Encontrados y Soluciones

Registro de problemas encontrados durante la configuración del sistema AI Lab.

## 1. GPU en D3cold

**Fecha:** 2026-08-27
**Severidad:** Alta
**Estado:** Resuelto

### Problema
La GPU NVIDIA entra en estado D3cold (bajo consumo) y no responde a peticiones de inferencia.

### Síntomas
- nvidia-smi no responde
- Servidor AI falla al iniciar
- VRAM no está disponible

### Causa
El sistema de energía del laptop activa D3cold para ahorrar batería.

### Solución
```bash
# Deshabilitar D3cold
echo 0 | sudo tee /sys/bus/pci/drivers/nvidia/*/d3cold_allowed

# Activar persistence mode
nvidia-smi -pm 1

# O usar el script automatizado
~/scripting/gpu-tools/gpu-performance.sh --on
```

### Prevención
El servicio `nvidia-max-performance.service` deshabilita D3cold al boot.

---

## 2. CUDA Out of Memory (OOM)

**Fecha:** 2026-08-28
**Severidad:** Alta
**Estado:** Resuelto

### Problema
Al usar CTX=32768 con NGL=40, el servidor crash por VRAM insuficiente.

### Síntomas
- Servidor se cierra inesperadamente
- Error de CUDA OOM en logs
- GPU memory: 7650MB / 8151MB (solo 101MB libre)

### Causa
40 GPU layers + CTX=32768 exceden la VRAM disponible (8GB).

### Solución
Reducir NGL de 40 a 30:
```bash
# Editar config
~/.config/gemma4-server.conf
NGL=30

# Reiniciar servidor
~/scripting/gpu-tools/gemma4-ctl.sh restart
```

### Resultado
- VRAM: 6141MB / 8151MB (2010MB libre)
- CTX=32768 funciona correctamente

---

## 3. MCP Server no carga tools

**Fecha:** 2026-08-29
**Severidad:** Media
**Estado:** Resuelto

### Problema
El servidor MCP no muestra las tools disponibles.

### Síntomas
- Solo 1 tool aparece en /tools
- Modelos no pueden usar herramientas

### Causa
El Python path no incluye el directorio de site-packages del venv.

### Solución
Agregar el path al inicio de system_mcp_server.py:
```python
venv_site = "/tmp/search-env/lib/python3.12/site-packages"
if os.path.exists(venv_site) and venv_site not in sys.path:
    sys.path.insert(0, venv_site)
```

---

## 4. Voice Input no funciona

**Fecha:** 2026-08-29
**Severidad:** Media
**Estado:** Resuelto

### Problema
Open WebUI no tiene entrada de voz configurada.

### Síntomas
- No hay botón de micrófono
- No se puede enviar audio

### Causa
Whisper no está instalado como servicio.

### Solución
1. Instalar faster-whisper
2. Crear whisper_server.py
3. Configurar servicio systemd
4. Configurar Open WebUI para usar http://localhost:9093

---

## 5. Web Search limitado

**Fecha:** 2026-08-29
**Severidad:** Media
**Estado:** Resuelto

### Problema
La herramienta de búsqueda web original (Brave browser) tiene limitaciones.

### Síntomas
- No retorna resultados directamente
- Solo abre el navegador
- No hay control de resultados

### Causa
La implementación original solo abría Brave browser.

### Solución
Implementar búsqueda con DuckDuckGo:
```python
from duckduckgo_search import DDGS
results = list(ddgs.text(query, max_results=5))
```

---

## 6. System Prompt no soportado

**Fecha:** 2026-08-29
**Severidad:** Baja
**Estado:** Workaround implementado

### Problema
llama.cpp no soporta el flag --system-prompt.

### Síntomas
- Error: "invalid argument: --system-prompt"
- Servidor no inicia

### Causa
La versión de llama.cpp no tiene este flag.

### Solución
Usar system prompt vía:
- Web UI de llama.cpp
- Configuración de Open WebUI
- Incluir en el system prompt del modelo

---

## 7. Docker permission denied

**Fecha:** 2026-08-29
**Severidad:** Baja
**Estado:** Workaround implementado

### Problema
Docker compose falla con "Permission denied".

### Síntomas
- No se pueden iniciar contenedores
- Error de conexión al socket de Docker

### Causa
El usuario no tiene permisos de Docker.

### Solución
Usar sudo o agregar el usuario al grupo docker:
```bash
sudo usermod -aG docker $USER
```

O usar alternativas sin Docker (ej: Whisper server nativo).

---

## 8. VBIOS power limit bloqueado

**Fecha:** 2026-08-27
**Severidad:** Baja
**Estado:** No resuelto (limitación de hardware)

### Problema
No se puede ajustar el power limit de la GPU.

### Síntomas
- nvidia-smi -pl falla
- Power limit fijo en 55W

### Causa
ASUS bloquea el VBIOS del laptop.

### Solución
No hay solución posible. Usar el power limit por defecto (55W).
