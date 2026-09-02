"""Browser automation and control tools"""

import os
import re

from mcp_common.logging import log_operation
from mcp_common.audit import record_system_error

TOOLS = [
    {
        "name": "browser_navigate",
        "description": "Navega a una URL utilizando el navegador headless Brave Browser y espera a que cargue.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL de destino a la que navegar."
                },
                "wait_seconds": {
                    "type": "number",
                    "description": "Segundos de espera tras la navegación (default: 3.0)."
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "browser_extract_text",
        "description": "Extrae el contenido textual legible de la página activa o de un selector CSS específico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "Selector CSS del elemento a extraer (default: 'body')."
                }
            }
        }
    },
    {
        "name": "browser_extract_markdown",
        "description": "Modo lectura avanzado: extrae el contenido esencial de la página web convertido a Markdown estructurado, omitiendo anuncios y elementos distractores.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "browser_click",
        "description": "Hace clic en un elemento web interactivo (botón, enlace, menú) mediante su selector CSS.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "Selector CSS del elemento a cliquear."
                }
            },
            "required": ["selector"]
        }
    },
    {
        "name": "browser_type",
        "description": "Escribe texto en un campo de entrada o formulario en la página web activa.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "selector": {
                    "type": "string",
                    "description": "Selector CSS del campo de texto / input."
                },
                "text": {
                    "type": "string",
                    "description": "Texto a ingresar."
                },
                "submit": {
                    "type": "boolean",
                    "description": "Si es true, envía el formulario tras escribir (default: false)."
                }
            },
            "required": ["selector", "text"]
        }
    },
    {
        "name": "browser_screenshot",
        "description": "Captura de pantalla de la página web activa y la guarda en la carpeta multimedia para visualización directa.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre opcional del archivo (default: screenshot_<timestamp>.png)."
                },
                "full_page": {
                    "type": "boolean",
                    "description": "Si es true, captura la página completa (scroll completo) (default: false)."
                }
            }
        }
    },
    {
        "name": "browser_print_pdf",
        "description": "Genera e imprime un documento PDF de alta fidelidad con el contenido de la página web activa.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre del archivo PDF de salida (ej: 'reporte.pdf')."
                }
            }
        }
    },
    {
        "name": "browser_get_links",
        "description": "Extrae todos los enlaces e hipervínculos presentes en la página web activa.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "browser_list_tabs",
        "description": "Lista todas las pestañas abiertas en el navegador headless.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "browser_sync_brave_profile",
        "description": "Sincroniza cookies, sesiones autenticadas e identidades desde el navegador personal Brave hacia el entorno de navegación de la IA.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile_name": {
                    "type": "string",
                    "description": "Nombre del perfil de Brave a sincronizar (default: 'Default')."
                }
            }
        }
    },
    {
        "name": "browser_clear_session",
        "description": "Limpia cookies y caché del navegador para iniciar una sesión anónima limpia (modo incógnito).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "browser_status",
        "description": "Consulta el estado actual de la sesión del navegador headless (URL actual, título, puerto CDP).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
]

# ── Handlers ───────────────────────────────────────────────
def _browser_navigate_handler(url: str, wait_seconds: float = 3.0) -> str:
    """Navega a una URL con el navegador headless Brave."""
    from mcp_common.security import is_safe_url
    if not is_safe_url(url):
        return "Error: URL no permitida (SSRF bloqueado — no se permiten IPs privadas o esquemas no seguros)"
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        res = engine.navigate(url, wait_seconds=wait_seconds)
        log_operation("browser_navigate", {"url": url}, f"title={res.get('title', '')}")
        return f"🌐 **Navegación Completada:**\n• **Título**: {res.get('title', 'N/A')}\n• **URL Final**: {res.get('url', url)}"
    except Exception as e:
        log_operation("browser_navigate", {"url": url}, f"ERROR: {e}")
        return f"Error en navegación web: {e}"



def _browser_extract_text_handler(selector: str = "body") -> str:
    """Extrae el contenido de texto legible de la página web activa."""
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        text = engine.extract_text(selector=selector)
        log_operation("browser_extract_text", {"selector": selector}, f"{len(text or '')} chars")
        if not text:
            return f"ℹ️ No se encontró contenido textual en el selector '{selector}'."
        preview = text[:3000]
        suffix = f"\n\n... *(truncado, {len(text)} caracteres totales)*" if len(text) > 3000 else ""
        return f"📄 **Contenido Extraído (`{selector}`):**\n\n{preview}{suffix}"
    except Exception as e:
        log_operation("browser_extract_text", {"selector": selector}, f"ERROR: {e}")
        return f"Error al extraer texto web: {e}"



def _browser_extract_markdown_handler() -> str:
    """Extrae el contenido de la página web convertido a Markdown limpio."""
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        md = engine.extract_markdown()
        log_operation("browser_extract_markdown", {}, f"{len(md or '')} chars")
        if not md:
            return "ℹ️ No se pudo extraer contenido Markdown de la página activa."
        preview = md[:4000]
        suffix = f"\n\n... *(documento truncado, {len(md)} caracteres totales)*" if len(md) > 4000 else ""
        return f"📖 **Lectura Markdown de Página Web:**\n\n{preview}{suffix}"
    except Exception as e:
        log_operation("browser_extract_markdown", {}, f"ERROR: {e}")
        return f"Error al extraer Markdown de la página: {e}"


def _sanitize_selector(selector: str) -> str:
    """Sanitize CSS selector to prevent JS injection."""
    return re.sub(r"[^a-zA-Z0-9_\-\.\s\[\]=\"\'\*\>\:\(\)\,\+\~\^\$]", "", selector)


def _browser_click_handler(selector: str) -> str:
    """Hace clic en un elemento web interactivo."""
    selector = _sanitize_selector(selector)
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        res = engine.click(selector=selector)
        log_operation("browser_click", {"selector": selector}, f"success={res.get('success')}")
        if res.get("success"):
            return f"✅ Clic ejecutado en elemento `<{res.get('tag', 'element')}>` (`{selector}`): {res.get('text', '')}"
        else:
            return f"❌ Error al hacer clic: {res.get('error', 'Elemento no interactuable')}"
    except Exception as e:
        log_operation("browser_click", {"selector": selector}, f"ERROR: {e}")
        return f"Error al hacer clic en elemento: {e}"



def _browser_type_handler(selector: str, text: str, submit: bool = False) -> str:
    """Escribe texto en un campo de entrada web."""
    selector = _sanitize_selector(selector)
    if len(text) > 100_000:
        return "Error: Texto demasiado largo (máximo 100,000 caracteres)"
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        res = engine.type_text(selector=selector, text=text, submit=submit)
        log_operation("browser_type", {"selector": selector, "length": len(text)}, f"success={res.get('success')}")
        if res.get("success"):
            sub_str = " y enviado formulario" if submit else ""
            return f"✅ Texto ({res['length']} caracteres) ingresado en `{selector}`{sub_str}."
        else:
            return f"❌ Error al escribir en selector `{selector}`: {res.get('error')}"
    except Exception as e:
        return f"Error al ingresar texto web: {e}"



def _browser_screenshot_handler(name: str = None, full_page: bool = False) -> str:
    """Captura de pantalla de la página web activa."""
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        res = engine.screenshot(name=name, full_page=full_page)
        log_operation("browser_screenshot", {"name": name, "full_page": full_page}, f"{res['size_bytes']} bytes")
        return f"📸 **Captura de Pantalla Guardada:**\n• **Archivo**: `{res['filename']}` ({res['size_bytes']} bytes)\n• **Ruta local**: `{res['file_path']}`\n\n💡 *Tip: Usa `media_view(file_path='{res['file_path']}')` para visualizar la imagen directamente en el chat.*"
    except Exception as e:
        log_operation("browser_screenshot", {"name": name}, f"ERROR: {e}")
        return f"Error al capturar screenshot: {e}"



def _browser_print_pdf_handler(filename: str = None) -> str:
    """Imprime la página web activa a un archivo PDF."""
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        res = engine.print_to_pdf(filename=filename)
        log_operation("browser_print_pdf", {"filename": filename}, f"{res['size_bytes']} bytes")
        return f"📄 **Documento PDF Generado:**\n• **Archivo**: `{res['filename']}` ({res['size_bytes']} bytes)\n• **Ruta local**: `{res['file_path']}`"
    except Exception as e:
        log_operation("browser_print_pdf", {"filename": filename}, f"ERROR: {e}")
        return f"Error al generar PDF de la página: {e}"



def _browser_get_links_handler() -> str:
    """Extrae todos los enlaces presentes en la página web."""
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        links = engine.get_links()
        log_operation("browser_get_links", {}, f"{len(links)} links")
        if not links:
            return "ℹ️ No se encontraron enlaces en la página web activa."
        output = f"🔗 **Enlaces Encontrados ({len(links)} totales):**\n\n"
        for idx, l in enumerate(links[:30], 1):
            output += f"{idx}. [{l['text']}]({l['href']})\n"
        if len(links) > 30:
            output += f"\n... *(y {len(links) - 30} enlaces más)*"
        return output.strip()
    except Exception as e:
        log_operation("browser_get_links", {}, f"ERROR: {e}")
        return f"Error al extraer enlaces: {e}"



def _browser_list_tabs_handler() -> str:
    """Lista las pestañas abiertas en el navegador."""
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        tabs = engine.list_tabs()
        log_operation("browser_list_tabs", {}, f"{len(tabs)} tabs")
        if not tabs:
            return "ℹ️ No hay pestañas abiertas en el navegador."
        output = f"📑 **Pestañas Abiertas ({len(tabs)}):**\n\n"
        for idx, t in enumerate(tabs, 1):
            output += f"{idx}. **`{t['title'] or '(sin título)'}`**\n   └── URL: {t['url']} (ID: `{t['id']}`)\n"
        return output.strip()
    except Exception as e:
        log_operation("browser_list_tabs", {}, f"ERROR: {e}")
        return f"Error al listar pestañas: {e}"



def _browser_sync_brave_profile_handler(profile_name: str = "Default") -> str:
    """Sincroniza el perfil, cookies e identidades desde Brave personal."""
    try:
        from scripts.tools.browser_engine import BraveIdentitySync
        res = BraveIdentitySync.sync_profile(profile_name=profile_name)
        log_operation("browser_sync_brave", {"profile": profile_name}, f"success={res.get('success')}")
        if res.get("success"):
            items_str = ", ".join(res.get("synced_items", []))
            return f"🔐 **Perfil de Brave Sincronizado Exitosamente:**\n• **Perfil**: `{profile_name}`\n• **Elementos**: {items_str}\n• **Destino**: `{res.get('target', 'N/A')}`\n\nLas sesiones autenticadas (cookies y local storage) ahora están activas para la navegación de la IA."
        else:
            return f"❌ Error al sincronizar perfil de Brave: {res.get('error')}"
    except Exception as e:
        log_operation("browser_sync_brave", {"profile": profile_name}, f"ERROR: {e}")
        return f"Error al sincronizar identidades de Brave: {e}"



def _browser_clear_session_handler() -> str:
    """Limpia cookies y caché del navegador para navegación anónima."""
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        res = engine.clear_session()
        log_operation("browser_clear_session", {}, "cleared")
        return f"🧹 {res.get('message', 'Sesión limpiada')}"
    except Exception as e:
        log_operation("browser_clear_session", {}, f"ERROR: {e}")
        return f"Error al limpiar sesión del navegador: {e}"


# ── Full-Duplex Voice & Multimodal Vision Tools ─────────────

def _browser_status_handler() -> str:
    """Consulta el estado del navegador headless."""
    try:
        from scripts.tools.browser_engine import BrowserEngine
        engine = BrowserEngine()
        st = engine.get_status()
        log_operation("browser_status", {}, f"active={st.get('browser_active')}")
        icon = "🟢" if st.get("browser_active") else "⚪"
        output = f"{icon} **Estado de Brave Headless:**\n\n"
        output += f"• **Activo**: {'Sí' if st.get('browser_active') else 'No (inicia bajo demanda)'}\n"
        output += f"• **Puerto CDP**: `{st['cdp_port']}`\n"
        output += f"• **URL Actual**: {st['current_url']}\n"
        output += f"• **Título**: {st['page_title'] or '(sin título)'}\n"
        return output
    except Exception as e:
        return f"Error al consultar estado del navegador: {e}"



HANDLERS = {
    "browser_navigate": _browser_navigate_handler,
    "browser_extract_text": _browser_extract_text_handler,
    "browser_extract_markdown": _browser_extract_markdown_handler,
    "browser_click": _browser_click_handler,
    "browser_type": _browser_type_handler,
    "browser_screenshot": _browser_screenshot_handler,
    "browser_print_pdf": _browser_print_pdf_handler,
    "browser_get_links": _browser_get_links_handler,
    "browser_list_tabs": _browser_list_tabs_handler,
    "browser_sync_brave_profile": _browser_sync_brave_profile_handler,
    "browser_clear_session": _browser_clear_session_handler,
    "browser_status": _browser_status_handler,
}
