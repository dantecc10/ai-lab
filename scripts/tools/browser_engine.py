#!/usr/bin/env python3
"""
AI Lab — Headless Browser & Identity Sync Engine (Brave CDP Driver)
Controla Brave Browser en modo headless mediante Chrome DevTools Protocol (CDP),
sincroniza cookies/identidades del perfil de usuario y captura contenido/pantallas.
"""

import os
import sys
import time
import json
import shutil
import sqlite3
import subprocess
import urllib.request
import asyncio
from pathlib import Path
from typing import Any

# Rutas
DEFAULT_BRAVE_USER_DATA = Path.home() / ".config" / "BraveSoftware" / "Brave-Browser"
AI_BROWSER_PROFILE_DIR = Path.home() / ".local" / "share" / "ai-lab" / "browser_profile"
MEDIA_DIR = Path.home() / ".local" / "share" / "ai-lab" / "media"
CDP_PORT = 9222

class BraveIdentitySync:
    """Sincronizador de identidades, cookies y sesiones desde Brave personal."""

    @staticmethod
    def sync_profile(source_dir: Path = DEFAULT_BRAVE_USER_DATA, target_dir: Path = AI_BROWSER_PROFILE_DIR, profile_name: str = "Default") -> dict:
        """Sincroniza cookies, local storage y preferencias hacia el perfil de AI Lab."""
        src_profile = source_dir / profile_name
        dst_profile = target_dir / profile_name
        
        if not src_profile.exists():
            return {
                "success": False,
                "error": f"Perfil de origen no encontrado en {src_profile}"
            }

        dst_profile.mkdir(parents=True, exist_ok=True)
        synced_items = []

        # 1. Copiar Local State (para claves criptográficas de sesión)
        local_state_src = source_dir / "Local State"
        if local_state_src.exists():
            try:
                shutil.copy2(local_state_src, target_dir / "Local State")
                synced_items.append("Local State")
            except Exception:
                pass

        # 2. Copiar Network/Cookies (Base de datos SQLite)
        cookies_src_dir = src_profile / "Network"
        cookies_dst_dir = dst_profile / "Network"
        if cookies_src_dir.exists():
            cookies_dst_dir.mkdir(parents=True, exist_ok=True)
            for f in cookies_src_dir.glob("Cookies*"):
                try:
                    shutil.copy2(f, cookies_dst_dir / f.name)
                    synced_items.append(f"Network/{f.name}")
                except Exception:
                    pass

        # 3. Copiar Local Storage
        ls_src = src_profile / "Local Storage"
        ls_dst = dst_profile / "Local Storage"
        if ls_src.exists():
            try:
                if ls_dst.exists():
                    shutil.rmtree(ls_dst, ignore_errors=True)
                shutil.copytree(ls_src, ls_dst, symlinks=True, ignore_dangling_symlinks=True)
                synced_items.append("Local Storage")
            except Exception:
                pass

        # 4. Copiar Sessions y Preferences
        for item in ["Preferences", "Secure Preferences"]:
            p_src = src_profile / item
            if p_src.exists():
                try:
                    shutil.copy2(p_src, dst_profile / item)
                    synced_items.append(item)
                except Exception:
                    pass

        return {
            "success": True,
            "profile_name": profile_name,
            "source": str(src_profile),
            "target": str(dst_profile),
            "synced_items": synced_items
        }


class BrowserEngine:
    """Motor de automatización y navegación web headless con Brave CDP."""

    def __init__(self, port: int = CDP_PORT, user_data_dir: Path = AI_BROWSER_PROFILE_DIR):
        self.port = port
        self.user_data_dir = user_data_dir
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        self.process: subprocess.Popen | None = None
        self._ws_url: str | None = None
        self._target_id: str | None = None

    def is_cdp_alive(self) -> bool:
        """Verifica si el puerto CDP responde."""
        try:
            url = f"http://127.0.0.1:{self.port}/json/version"
            req = urllib.request.Request(url, headers={"User-Agent": "AI-Lab-Browser"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def start_browser(self, headless: bool = True) -> bool:
        """Inicia el proceso de Brave Browser en modo headless con depuración remota."""
        if self.is_cdp_alive():
            return True

        brave_bin = shutil.which("brave-browser") or shutil.which("brave") or shutil.which("google-chrome") or shutil.which("chromium")
        if not brave_bin:
            raise FileNotFoundError("No se encontró el ejecutable de Brave Browser o Chromium en PATH.")

        cmd = [
            brave_bin,
            f"--remote-debugging-port={self.port}",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--mute-audio",
            "--hide-scrollbars",
            "--window-size=1920,1080"
        ]
        if headless:
            cmd.append("--headless=new")

        self.process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None
        )

        # Esperar a que el puerto responda
        for _ in range(30):
            if self.is_cdp_alive():
                return True
            time.sleep(0.2)
        return False

    def stop_browser(self):
        """Detiene el navegador headless."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2.0)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass
            self.process = None

    def _get_active_tab(self) -> dict:
        """Obtiene o crea una pestaña activa con WebSocket debugger."""
        self.start_browser()
        url = f"http://127.0.0.1:{self.port}/json/list"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            tabs = json.loads(resp.read().decode())
            # Filtrar pestañas tipo 'page'
            pages = [t for t in tabs if t.get("type") == "page"]
            if pages:
                self._target_id = pages[0]["id"]
                self._ws_url = pages[0]["webSocketDebuggerUrl"]
                return pages[0]

        # Crear nueva pestaña si no hay
        new_url = f"http://127.0.0.1:{self.port}/json/new"
        req = urllib.request.Request(new_url, data=b"", method="PUT")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            new_tab = json.loads(resp.read().decode())
            self._target_id = new_tab["id"]
            self._ws_url = new_tab["webSocketDebuggerUrl"]
            return new_tab

    async def _send_cdp_command_async(self, method: str, params: dict | None = None) -> dict:
        """Envía un comando CDP a través de WebSockets de forma asíncrona."""
        import websockets
        tab = self._get_active_tab()
        ws_url = tab["webSocketDebuggerUrl"]

        msg_id = int(time.time() * 1000) % 1000000
        payload = {
            "id": msg_id,
            "method": method,
            "params": params or {}
        }

        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            await ws.send(json.dumps(payload))
            while True:
                resp_text = await asyncio.wait_for(ws.recv(), timeout=15.0)
                resp = json.loads(resp_text)
                if resp.get("id") == msg_id:
                    return resp

    def send_cdp(self, method: str, params: dict | None = None) -> dict:
        """Envía un comando CDP síncronamente."""
        return asyncio.run(self._send_cdp_command_async(method, params))

    # ── Métodos de Alto Nivel ────────────────────────────────
    def navigate(self, url: str, wait_seconds: float = 3.0) -> dict:
        """Navega a una URL y espera a que cargue el contenido."""
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url

        res = self.send_cdp("Page.navigate", {"url": url})
        time.sleep(wait_seconds)

        eval_res = self.send_cdp("Runtime.evaluate", {
            "expression": "JSON.stringify({url: window.location.href, title: document.title})"
        })
        info = {}
        try:
            val_str = eval_res.get("result", {}).get("result", {}).get("value", "{}")
            info = json.loads(val_str)
        except Exception:
            pass

        return {
            "status": "success",
            "url": info.get("url", url),
            "title": info.get("title", ""),
            "cdp_response": res.get("result", {})
        }

    def extract_text(self, selector: str = "body") -> str:
        """Extrae el contenido de texto legible de un selector."""
        js_expr = f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return 'Elemento no encontrado: {selector}';
            return el.innerText || el.textContent || '';
        }})()
        """
        res = self.send_cdp("Runtime.evaluate", {"expression": js_expr})
        return res.get("result", {}).get("result", {}).get("value", "")

    def click(self, selector: str) -> dict:
        """Hace clic en un elemento especificado por selector CSS."""
        js_expr = f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return {{success: false, error: 'Elemento no encontrado: {selector}'}};
            el.scrollIntoView({{behavior: 'instant', block: 'center'}});
            el.click();
            return {{success: true, tag: el.tagName, text: el.innerText ? el.innerText.substring(0, 50) : ''}};
        }})()
        """
        res = self.send_cdp("Runtime.evaluate", {"expression": js_expr, "returnByValue": True})
        return res.get("result", {}).get("result", {}).get("value", {"success": False})

    def type_text(self, selector: str, text: str, submit: bool = False) -> dict:
        """Escribe texto en un campo de formulario."""
        escaped_text = json.dumps(text)
        js_expr = f"""
        (() => {{
            const el = document.querySelector('{selector}');
            if (!el) return {{success: false, error: 'Elemento no encontrado: {selector}'}};
            el.focus();
            el.value = {escaped_text};
            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
            if ({str(submit).lower()} && el.form) {{
                el.form.submit();
            }}
            return {{success: true, selector: '{selector}', length: {len(text)}}};
        }})()
        """
        res = self.send_cdp("Runtime.evaluate", {"expression": js_expr, "returnByValue": True})
        return res.get("result", {}).get("result", {}).get("value", {"success": False})

    def screenshot(self, name: str | None = None, full_page: bool = False) -> dict:
        """Toma una captura de pantalla y la guarda en la carpeta multimedia."""
        import base64
        filename = name or f"screenshot_{int(time.time())}.png"
        if not filename.endswith(".png"):
            filename += ".png"
        target_path = MEDIA_DIR / filename

        params = {"format": "png"}
        if full_page:
            # Obtener altura total del documento
            metrics = self.send_cdp("Page.getLayoutMetrics")
            content_size = metrics.get("result", {}).get("contentSize", {})
            if content_size:
                params["clip"] = {
                    "x": 0, "y": 0,
                    "width": content_size.get("width", 1920),
                    "height": content_size.get("height", 1080),
                    "scale": 1
                }

        res = self.send_cdp("Page.captureScreenshot", params)
        b64_data = res.get("result", {}).get("data", "")
        if not b64_data:
            raise RuntimeError("Error al capturar screenshot desde CDP")

        img_bytes = base64.b64decode(b64_data)
        target_path.write_bytes(img_bytes)

        return {
            "status": "success",
            "file_path": str(target_path),
            "filename": filename,
            "size_bytes": len(img_bytes)
        }

    def extract_markdown(self) -> str:
        """Extrae el contenido principal de la página convertido a formato Markdown limpio."""
        js_expr = """
        (() => {
            const clone = document.body.cloneNode(true);
            // Remover scripts, styles, iframes, nav, footer, headers distractores
            clone.querySelectorAll('script, style, noscript, nav, footer, header, svg, iframe, .ad, .ads, [role="banner"], [role="navigation"]').forEach(el => el.remove());
            
            function nodeToMd(node) {
                if (node.nodeType === Node.TEXT_NODE) {
                    return node.textContent.replace(/\\s+/g, ' ');
                }
                if (node.nodeType !== Node.ELEMENT_NODE) return '';

                const tag = node.tagName.toLowerCase();
                let inner = Array.from(node.childNodes).map(nodeToMd).join('').trim();
                if (!inner && !['img', 'hr', 'br'].includes(tag)) return '';

                switch (tag) {
                    case 'h1': return `\\n# ${inner}\\n\\n`;
                    case 'h2': return `\\n## ${inner}\\n\\n`;
                    case 'h3': return `\\n### ${inner}\\n\\n`;
                    case 'h4': return `\\n#### ${inner}\\n\\n`;
                    case 'p': return `\\n${inner}\\n\\n`;
                    case 'li': return `\\n* ${inner}`;
                    case 'ul': case 'ol': return `\\n${inner}\\n\\n`;
                    case 'blockquote': return `\\n> ${inner}\\n\\n`;
                    case 'pre': case 'code': return `\\n\\`\\`\\`\\n${node.innerText || inner}\\n\\`\\`\\`\\n\\n`;
                    case 'a': return node.href ? `[${inner || node.href}](${node.href})` : inner;
                    case 'strong': case 'b': return `**${inner}**`;
                    case 'em': case 'i': return `*${inner}*`;
                    case 'br': return `\\n`;
                    case 'hr': return `\\n---\\n`;
                    default: return inner;
                }
            }

            let md = nodeToMd(clone);
            return md.replace(/\\n{3,}/g, '\\n\\n').trim();
        })()
        """
        res = self.send_cdp("Runtime.evaluate", {"expression": js_expr, "returnByValue": True})
        return res.get("result", {}).get("result", {}).get("value", "")

    def print_to_pdf(self, filename: str | None = None) -> dict:
        """Imprime la página web activa a un documento PDF de alta fidelidad."""
        import base64
        filename = filename or f"webpage_{int(time.time())}.pdf"
        if not filename.endswith(".pdf"):
            filename += ".pdf"
        target_path = MEDIA_DIR / filename

        res = self.send_cdp("Page.printToPDF", {
            "printBackground": True,
            "preferCSSPageSize": True
        })
        b64_data = res.get("result", {}).get("data", "")
        if not b64_data:
            raise RuntimeError("Error al generar PDF mediante CDP")

        pdf_bytes = base64.b64decode(b64_data)
        target_path.write_bytes(pdf_bytes)

        return {
            "status": "success",
            "file_path": str(target_path),
            "filename": filename,
            "size_bytes": len(pdf_bytes)
        }

    def get_links(self, filter_domain: bool = False) -> list[dict]:
        """Extrae todos los enlaces presentes en la página web."""
        js_expr = """
        (() => {
            const links = [];
            const seen = new Set();
            document.querySelectorAll('a[href]').forEach(a => {
                const href = a.href;
                const text = a.innerText.trim();
                if (href && !href.startsWith('javascript:') && !seen.has(href)) {
                    seen.add(href);
                    links.push({ text: text || '(sin texto)', href: href });
                }
            });
            return links;
        })()
        """
        res = self.send_cdp("Runtime.evaluate", {"expression": js_expr, "returnByValue": True})
        links = res.get("result", {}).get("result", {}).get("value", [])
        return links

    def new_tab(self, url: str = "about:blank") -> dict:
        """Abre una nueva pestaña en el navegador."""
        self.start_browser()
        encoded_url = urllib.parse.quote(url, safe="") if hasattr(urllib, "parse") else url
        endpoint = f"http://127.0.0.1:{self.port}/json/new?{encoded_url}"
        req = urllib.request.Request(endpoint, data=b"", method="PUT")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            tab = json.loads(resp.read().decode())
            self._target_id = tab["id"]
            self._ws_url = tab.get("webSocketDebuggerUrl")
            return {
                "status": "success",
                "target_id": tab["id"],
                "url": tab.get("url", url),
                "title": tab.get("title", "")
            }

    def list_tabs(self) -> list[dict]:
        """Lista todas las pestañas activas en el navegador."""
        if not self.is_cdp_alive():
            return []
        url = f"http://127.0.0.1:{self.port}/json/list"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            tabs = json.loads(resp.read().decode())
            return [{
                "id": t["id"],
                "type": t.get("type", "page"),
                "title": t.get("title", ""),
                "url": t.get("url", "")
            } for t in tabs if t.get("type") == "page"]

    def close_tab(self, target_id: str | None = None) -> dict:
        """Cierra una pestaña específica o la pestaña actual."""
        tid = target_id or self._target_id
        if not tid:
            return {"status": "error", "message": "No hay pestaña activa identificada"}

        url = f"http://127.0.0.1:{self.port}/json/close/{tid}"
        try:
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                res_text = resp.read().decode()
                self._target_id = None
                self._ws_url = None
                return {"status": "success", "closed_id": tid, "response": res_text}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def clear_session(self) -> dict:
        """Limpia cookies y cache para iniciar una sesión anónima limpia."""
        self.send_cdp("Network.clearBrowserCookies")
        self.send_cdp("Network.clearBrowserCache")
        return {"status": "success", "message": "Cookies y caché del navegador eliminados. Modo incógnito activo."}

    def evaluate(self, script: str) -> Any:
        """Ejecuta código JavaScript arbitrario en la página activa."""
        res = self.send_cdp("Runtime.evaluate", {"expression": script, "returnByValue": True})
        return res.get("result", {}).get("result", {}).get("value")

    def get_status(self) -> dict:
        """Devuelve el estado actual de la sesión del navegador."""
        active = self.is_cdp_alive()
        tab_info = {}
        if active:
            try:
                eval_res = self.send_cdp("Runtime.evaluate", {
                    "expression": "JSON.stringify({url: window.location.href, title: document.title})"
                })
                tab_info = json.loads(eval_res.get("result", {}).get("result", {}).get("value", "{}"))
            except Exception:
                pass

        return {
            "browser_active": active,
            "cdp_port": self.port,
            "user_data_dir": str(self.user_data_dir),
            "current_url": tab_info.get("url", "about:blank"),
            "page_title": tab_info.get("title", "")
        }

if __name__ == "__main__":
    engine = BrowserEngine()
    print(f"[+] Iniciando BrowserEngine con Brave en puerto CDP {engine.port}...")
    
    # 1. Sincronizar perfil de Brave si existe
    sync_res = BraveIdentitySync.sync_profile()
    print(f"[+] Sincronización de perfil Brave: {sync_res['success']} ({len(sync_res.get('synced_items', []))} elementos)")

    # 2. Navegación de prueba
    print("[+] Navegando a https://duckduckgo.com...")
    nav_res = engine.navigate("https://duckduckgo.com")
    print(f"[✓] Página cargada: '{nav_res['title']}' ({nav_res['url']})")

    # 3. Screenshot de prueba
    ss_res = engine.screenshot("test_duckduckgo.png")
    print(f"[✓] Captura guardada en: {ss_res['file_path']} ({ss_res['size_bytes']} bytes)")

    # 4. Estado
    status = engine.get_status()
    print(f"[✓] Estado del navegador: {status}")
