# MCP Modular Architecture

Documentación técnica de la arquitectura modular del servidor MCP (Model Context Protocol) de AI Lab.

---

## 1. Visión General

El orquestador MCP (`scripts/tools/mcp_server.py`) reemplaza el monolito `system_mcp_server.py` (11,926 líneas) con una arquitectura modular de **18 domain modules** y **6 shared utilities**, exponiendo **215 herramientas únicas** a través de JSON-RPC 2.0 sobre stdio.

### Por qué modular

| Problema del monolito | Solución modular |
|----------------------|------------------|
| 11,926 líneas en un archivo | 18 archivos de ~200-800 líneas c/u |
| Difícil de mantener y navegar | Cada dominio es autocontenido |
| Agregar una tool = editar el monolito | Crear archivo `.py` en `mcp_domain/` |
| Un bug puede romper todo | Aislamiento por dominio |
| Imports circulares posibles | Dependencias claras por módulo |

---

## 2. Estructura de Directorios

```
scripts/tools/
├── mcp_server.py                  # Orquestador principal (~245 líneas)
├── mcp_common/                    # Utilidades compartidas (6 módulos)
│   ├── __init__.py
│   ├── paths.py                   # HOME, safe_path(), format_size()
│   ├── crypto.py                  # encrypt_value(), decrypt_value() (Fernet)
│   ├── security.py                # is_safe_url(), sanitize_path(), is_blocked_command()
│   ├── logging.py                 # log_operation() — audit trail
│   ├── notifications.py           # load_notify_config(), should_notify()
│   └── keyboard.py                # flash_keyboard_status() — ASUS ROG LED
├── mcp_domain/                    # Domain modules (18 módulos)
│   ├── __init__.py                # load_all_domains() — auto-discovery
│   ├── filesystem.py              # 13 tools — archivos, directorios, run_command
│   ├── system.py                  # 21 tools — sistema, GPU, procesos, cron
│   ├── memory.py                  # 6 tools — memoria persistente SQLite
│   ├── spotify.py                 # 12 tools — control completo de Spotify
│   ├── smart_home.py              # 21 tools — Kasa plugs, teclado, sleep routine
│   ├── devops.py                  # 31 tools — GitHub, Git, Docker, análisis código
│   ├── network.py                 # 11 tools — ping, DNS, SSL, WHOIS, port scan
│   ├── voice_vision.py            # 21 tools — voz, visión multimodal, OCR
│   ├── web_search.py              # 9 tools — DuckDuckGo, Google, HTTP requests
│   ├── browser.py                 # 12 tools — Brave headless, CDP, screenshots
│   ├── communication.py           # 13 tools — notificaciones, email, WhatsApp
│   ├── chatshare.py               # 9 tools — exportar chats, R2 storage
│   ├── database.py                # 9 tools — SQL, CSV, JSON, PDF
│   ├── security_tools.py          # 5 tools — auditoría, secret detection
│   ├── osint.py                   # 5 tools — OSINT username/email/domain/IP
│   ├── ssh.py                     # 8 tools — SSH, tunnels, sync
│   ├── workflow.py                # 3 tools — DAG pipelines
│   ├── vector.py                  # 4 tools — búsqueda semántica RAG
│   └── delegation.py              # 2 tools — sub-agente E4B
├── browser_engine.py              # Motor Brave CDP (no es domain module)
└── system_mcp_server.py           # Monolito original (backup)
```

---

## 3. Cómo Funciona el Auto-Discovery

El `__init__.py` de `mcp_domain/` usa `pkgutil` para descubrir automáticamente todos los módulos:

```python
# mcp_domain/__init__.py
import pkgutil
import importlib

def load_all_domains():
    all_tools = []
    all_handlers = {}

    for importer, module_name, is_pkg in pkgutil.iter_modules(__path__):
        if module_name.startswith("_"):
            continue
        mod = importlib.import_module(f"mcp_domain.{module_name}")
        if hasattr(mod, "TOOLS"):
            all_tools.extend(mod.TOOLS)
        if hasattr(mod, "HANDLERS"):
            all_handlers.update(mod.HANDLERS)

    return all_tools, all_handlers
```

### Flujo de carga

```
mcp_server.py inicia
    │
    ├── load_all_domains()
    │       │
    │       ├── pkgutil.iter_modules() → encuentra 18 módulos
    │       │
    │       ├── importlib.import_module("mcp_domain.filesystem")
    │       │       └── extiende all_tools con 13 tools
    │       │       └── extiende all_handlers con 13 handlers
    │       │
    │       ├── importlib.import_module("mcp_domain.system")
    │       │       └── extiende all_tools con 21 tools
    │       │       └── extiende all_handlers con 21 handlers
    │       │
    │       └── ... (16 módulos más)
    │
    └── ALL_TOOLS = [215 tools]
        ALL_HANDLERS = {215 handlers}
```

---

## 4. Dispatcher de Handlers

El orquestador usa introspección de firmas para llamar correctamente a cada handler:

```python
# mcp_server.py
import inspect

def _call_handler(handler, arguments):
    """Call handler with correct signature: named params or args dict."""
    sig = inspect.signature(handler)
    params = list(sig.parameters.keys())
    if len(params) == 1 and params[0] == 'args':
        return handler(arguments)        # Handler expects dict
    return handler(**arguments)          # Handler expects named params
```

### Por qué es necesario

Los handlers tienen dos patrones de firma:

| Patrón | Ejemplo | Usado por |
|--------|---------|-----------|
| Named params | `def _web_search_handler(query: str, max_results: int = 5)` | web_search, fetch_article, browser, ssh, osint |
| Args dict | `def _browse_web_handler(args): url = args["url"]` | browse_web, http_request, smart_home, system |

El dispatcher detecta automáticamente cuál patrón usa el handler y lo llama correctamente.

---

## 5. Seguridad

### 5.1. SSRF Protection (`is_safe_url`)

```python
# mcp_common/security.py
BLOCKED_URL_SCHEMES = ("file://", "javascript:", "data:", "ftp://")
PRIVATE_IP_RE = re.compile(
    r"^(127\.\d|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|169\.254\.|0\.|localhost)"
)

def is_safe_url(url: str) -> bool:
    if any(url.startswith(s) for s in BLOCKED_URL_SCHEMES):
        return False
    parsed = urlparse(url)
    hostname = parsed.hostname or ""
    if PRIVATE_IP_RE.match(hostname):
        return False
    return True
```

**Uso en:** `browse_web`, `http_request`, `browser_navigate`

### 5.2. Path Traversal (`sanitize_path`)

```python
def sanitize_path(path: str) -> str:
    normalized = os.path.normpath(path)
    if ".." in normalized.split(os.sep):
        raise ValueError(f"Path traversal not allowed: {path}")
    return normalized
```

### 5.3. CSS Selector Sanitization

```python
# mcp_domain/browser.py
def _sanitize_selector(selector: str) -> str:
    """Sanitize CSS selector to prevent JS injection."""
    return re.sub(r"[^a-zA-Z0-9_\-\.\s\[\]=\"\'\*\>\:\(\)\,\+\~\^\$]", "", selector)
```

**Uso en:** `browser_click`, `browser_type`

### 5.4. Command Injection Prevention

| Herramienta | Antes (inseguro) | Después (seguro) |
|-------------|------------------|------------------|
| `_timer` | `f"subprocess.run(['notify-send', '{message}'])"` | `json.dumps(message)` |
| `_process_kill` | `f"pkill -{signal} {name}" shell=True` | `["pkill", f"-{signal}", name]` |
| `_system_shutdown` | `f"shutdown -h now" shell=True` | `["shutdown", "-h", "now"]` |
| `chmod` | `f"chmod {mode} {path}" shell=True` | `os.chmod(path, int(mode, 8))` |
| SSH tunnel | `f"ssh ... {user}@{host}" shell=True` | `["ssh", ..., f"{user}@{host}"]` |

---

## 6. Cómo Agregar un Nuevo Domain Module

### Paso 1: Crear el archivo

Crear `scripts/tools/mcp_domain/mi_dominio.py`:

```python
"""Mi dominio personalizado"""

from mcp_common.paths import HOME
from mcp_common.logging import log_operation

TOOLS = [
    {
        "name": "mi_tool",
        "description": "Descripción de la tool.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "param1": {
                    "type": "string",
                    "description": "Parámetro de ejemplo."
                }
            },
            "required": ["param1"]
        }
    }
]

def _mi_tool_handler(param1: str) -> str:
    try:
        result = f"Hola {param1}"
        log_operation("mi_tool", {"param1": param1}, "OK")
        return result
    except Exception as e:
        log_operation("mi_tool", {"param1": param1}, f"ERROR: {e}")
        return f"Error: {e}"

HANDLERS = {
    "mi_tool": _mi_tool_handler,
}
```

### Paso 2: Reiniciar

```bash
~/scripting/gpu-tools/gemma4-ctl.sh restart
```

El orquestador descubrirá automáticamente el nuevo módulo y registrará las tools.

### Convenciones

| Convención | Detalle |
|------------|---------|
| Nombre del archivo | `snake_case.py` (ej: `mi_dominio.py`) |
| TOOLS | Lista de dicts con `name`, `description`, `inputSchema` |
| HANDLERS | Dict `{tool_name: handler_function}` |
| Handler signature | Named params preferidos: `def _tool_handler(param: str, opt: int = 0) -> str` |
| Logging | Siempre llamar `log_operation()` en éxito y error |
| Imports | Usar `from mcp_common.X import Y` (no `scripts.tools.mcp_common`) |

---

## 7. Migración desde system_mcp_server.py

### Configuración del MCP server

En `~/.config/mcp-servers.json`:

```json
{
  "system": {
    "command": "python3",
    "args": ["/home/darkseid/scripting/gpu-tools/skills/mcp_server.py"],
    "cwd": "/home/darkseid/scripting/gpu-tools/skills"
  }
}
```

### Backup

El monolito original se mantiene como backup en:
- `/home/darkseid/ai-lab/scripts/tools/system_mcp_server.py`
- `/home/darkseid/scripting/gpu-tools/skills/system_mcp_server.py`

Para revertir, cambiar `mcp_server.py` → `system_mcp_server.py` en `mcp-servers.json`.

---

## 8. Troubleshooting

### Las tools no aparecen

```bash
# Verificar que el orchestrator carga correctamente
cd ~/scripting/gpu-tools/skills
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python3 mcp_server.py 2>/dev/null | python3 -c "import sys,json; d=json.load(sys.stdin); print(len(d['result']['tools']), 'tools')"
```

### Error de import en un domain module

```bash
# Probar import directo
cd ~/scripting/gpu-tools/skills
python3 -c "from mcp_domain.mi_dominio import TOOLS, HANDLERS; print(f'{len(TOOLS)} tools, {len(HANDLERS)} handlers')"
```

### Handler no recibe argumentos correctamente

Verificar que el handler usa el patrón correcto:
- Named params: `def _handler(param1: str, param2: int = 0)` → el orchestrator hace `handler(**arguments)`
- Args dict: `def _handler(args): value = args["param1"]` → el orchestrator hace `handler(arguments)`
