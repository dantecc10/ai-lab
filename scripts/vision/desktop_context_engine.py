#!/usr/bin/env python3
"""
AI Lab — Multi-Monitor, Window & Region-Aware Visual Intelligence Engine
Identifica pantallas múltiples, ventanas activas, regiones de interfaz (UI),
extrae contexto visual/OCR y genera asistencia proactiva con sugerencias de acción.
"""

import os
import re
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

# Asegurar que la raíz del proyecto ai-lab esté en sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MEDIA_DIR = Path.home() / ".local" / "share" / "ai-lab" / "media"

class DesktopContextEngine:
    """Motor de inspección contextual de pantallas múltiples, ventanas y elementos de UI."""

    def __init__(self):
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    def list_monitors(self) -> list[dict]:
        """Detecta y lista todos los monitores y pantallas conectadas con sus geometrías."""
        monitors = []
        if not shutil.which("xrandr"):
            return monitors

        try:
            res = subprocess.run(["xrandr", "--query"], capture_output=True, text=True, timeout=2.0)
            for line in res.stdout.splitlines():
                if " connected" in line:
                    # Ejemplo: "DP-2 connected 1920x1080+0+0 (normal...) 700mm x 390mm"
                    # O: "eDP-1 connected primary 1920x1200+1920+0 ..."
                    parts = line.split()
                    name = parts[0]
                    is_primary = "primary" in line
                    
                    # Extraer WxH+X+Y
                    geom_match = re.search(r"(\d+)x(\d+)\+(\d+)\+(\d+)", line)
                    if geom_match:
                        w, h, x, y = map(int, geom_match.groups())
                        monitors.append({
                            "name": name,
                            "width": w,
                            "height": h,
                            "x": x,
                            "y": y,
                            "geometry": f"{w}x{h}+{x}+{y}",
                            "is_primary": is_primary,
                            "is_connected": True
                        })
                    else:
                        monitors.append({
                            "name": name,
                            "width": 1920,
                            "height": 1080,
                            "x": 0,
                            "y": 0,
                            "geometry": "1920x1080+0+0",
                            "is_primary": is_primary,
                            "is_connected": True
                        })
        except Exception:
            pass

        return monitors

    def list_windows(self) -> list[dict]:
        """Lista todas las ventanas abiertas en el escritorio con su estado de foco y aplicación."""
        windows = []
        focused_wid = self.get_active_window_id()

        # 1. Intentar con wmctrl
        if shutil.which("wmctrl"):
            try:
                res = subprocess.run(["wmctrl", "-l", "-p", "-G"], capture_output=True, text=True, timeout=2.0)
                for line in res.stdout.splitlines():
                    # Formato: 0x03800003  0 2308  1920 0 1920 1080 pop-os Title
                    parts = line.split(maxsplit=7)
                    if len(parts) >= 8:
                        wid_hex, desktop, pid, x, y, w, h, title = parts
                        wid_dec = str(int(wid_hex, 16))
                        is_focused = (wid_hex.lower() == str(focused_wid).lower() or wid_dec == str(focused_wid))
                        
                        # Obtener clase de aplicación si xprop está disponible
                        wm_class = self.get_window_class(wid_hex)
                        
                        windows.append({
                            "window_id": wid_hex,
                            "window_id_dec": wid_dec,
                            "pid": pid,
                            "app_class": wm_class,
                            "title": title,
                            "geometry": {"x": int(x), "y": int(y), "width": int(w), "height": int(h)},
                            "is_focused": is_focused
                        })
                if windows:
                    return windows
            except Exception:
                pass

        # 2. Fallback con xdotool
        if shutil.which("xdotool"):
            try:
                res = subprocess.run(["xdotool", "search", "--onlyvisible", "--name", ""], capture_output=True, text=True, timeout=2.0)
                for wid in res.stdout.strip().splitlines():
                    if not wid.strip():
                        continue
                    try:
                        title_res = subprocess.run(["xdotool", "getwindowname", wid], capture_output=True, text=True, timeout=1.0)
                        title = title_res.stdout.strip()
                        if title:
                            is_focused = (wid == str(focused_wid))
                            windows.append({
                                "window_id": hex(int(wid)),
                                "window_id_dec": wid,
                                "pid": "unknown",
                                "app_class": self.get_window_class(wid),
                                "title": title,
                                "geometry": {"x": 0, "y": 0, "width": 1920, "height": 1080},
                                "is_focused": is_focused
                            })
                    except Exception:
                        pass
            except Exception:
                pass

        return windows

    def get_active_window_id(self) -> str | None:
        """Obtiene el identificador de la ventana activa actualmente con foco."""
        if shutil.which("xdotool"):
            try:
                res = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=1.5)
                if res.returncode == 0 and res.stdout.strip():
                    return res.stdout.strip()
            except Exception:
                pass
        return None

    def get_window_class(self, window_id: str) -> str:
        """Obtiene la clase de ventana (WM_CLASS) mediante xprop."""
        if shutil.which("xprop"):
            try:
                res = subprocess.run(["xprop", "-id", str(window_id), "WM_CLASS"], capture_output=True, text=True, timeout=1.0)
                # Formato: WM_CLASS(STRING) = "brave-browser", "Brave-browser"
                match = re.search(r'=\s*"(.*?)",\s*"(.*?)"', res.stdout)
                if match:
                    return match.group(2)
            except Exception:
                pass
        return "Unknown"

    def capture_target(self, target: str = "active_window", monitor_name: str | None = None,
                       window_id: str | None = None, bbox: dict | None = None, filename: str | None = None) -> Path:
        """Captura un objetivo específico: ventana activa, monitor concreto, ventana por ID o región bbox."""
        fname = filename or f"inspect_{target}_{int(time.time())}.png"
        if not fname.endswith(".png"):
            fname += ".png"
        out_path = MEDIA_DIR / fname

        env = os.environ.copy()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"

        # 1. Capturar ventana activa
        if target == "active_window":
            active_id = window_id or self.get_active_window_id()
            if active_id and shutil.which("import"):
                try:
                    res = subprocess.run(["import", "-window", str(active_id), str(out_path)], env=env, capture_output=True, timeout=3.0)
                    if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                        return out_path
                except Exception:
                    pass
            if shutil.which("gnome-screenshot"):
                try:
                    res = subprocess.run(["gnome-screenshot", "-w", "-f", str(out_path)], env=env, capture_output=True, timeout=3.0)
                    if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                        return out_path
                except Exception:
                    pass

        # 2. Capturar monitor específico (crop de pantalla completa)
        if target == "monitor" and monitor_name:
            monitors = self.list_monitors()
            target_mon = next((m for m in monitors if m["name"].lower() == monitor_name.lower()), None)
            if target_mon and shutil.which("import"):
                full_path = MEDIA_DIR / f"full_{fname}"
                try:
                    subprocess.run(["import", "-window", "root", str(full_path)], env=env, capture_output=True, timeout=3.0)
                    if full_path.exists():
                        # Recortar con ImageMagick crop
                        crop_geom = target_mon["geometry"]
                        subprocess.run(["convert", str(full_path), "-crop", crop_geom, "+repage", str(out_path)], timeout=3.0)
                        if out_path.exists() and out_path.stat().st_size > 0:
                            full_path.unlink(missing_ok=True)
                            return out_path
                except Exception:
                    pass

        # 3. Capturar región rectangular personalizada (bbox)
        if target == "bbox" and bbox and shutil.which("import"):
            full_path = MEDIA_DIR / f"full_{fname}"
            try:
                subprocess.run(["import", "-window", "root", str(full_path)], env=env, capture_output=True, timeout=3.0)
                if full_path.exists():
                    crop_geom = f"{bbox.get('width', 800)}x{bbox.get('height', 600)}+{bbox.get('x', 0)}+{bbox.get('y', 0)}"
                    subprocess.run(["convert", str(full_path), "-crop", crop_geom, "+repage", str(out_path)], timeout=3.0)
                    if out_path.exists() and out_path.stat().st_size > 0:
                        full_path.unlink(missing_ok=True)
                        return out_path
            except Exception:
                pass

        # 4. Fallback a captura de escritorio completa
        from scripts.vision.multimodal_vision import MultimodalVisionEngine
        return MultimodalVisionEngine().capture_screen(filename=fname)

    def explain_context(self, target: str = "active_window", user_intent: str = "¿Qué estoy haciendo y qué opciones tengo?",
                        include_rag: bool = True) -> dict:
        """Inspecciona visualmente el objetivo, detecta la ventana/app activa, OCR y sugiere acciones proactivas."""
        # 1. Obtener ventana activa y contexto
        windows = self.list_windows()
        focused_win = next((w for w in windows if w["is_focused"]), None)
        monitors = self.list_monitors()

        # 2. Capturar objetivo
        shot_path = self.capture_target(target=target)

        # 3. Procesar OCR y análisis multimodal
        from scripts.vision.multimodal_vision import MultimodalVisionEngine
        vision_engine = MultimodalVisionEngine()
        ocr_text = vision_engine.run_ocr(shot_path)
        
        prompt = (
            f"El usuario pregunta: '{user_intent}'.\n"
            f"Ventana detectada: '{focused_win['title'] if focused_win else 'Desconocida'}' "
            f"(App: {focused_win['app_class'] if focused_win else 'Escritorio'}).\n"
            "Analiza detalladamente lo que el usuario está viendo en esta pantalla o ventana, "
            "identifica las opciones/botones visibles y redacta sugerencias claras de qué puede hacer a continuación."
        )
        visual_analysis = vision_engine.analyze_image(shot_path, prompt=prompt)

        # 4. Consultar documentación local (RAG) si aplica
        rag_context = []
        if include_rag and focused_win:
            try:
                from scripts.tools.vector_engine import VectorEngine
                app_name = focused_win.get("app_class", "")
                query = f"{app_name} {focused_win.get('title', '')} {ocr_text[:80]}"
                results = VectorEngine().search(query, limit=2)
                rag_context = [r["text"] for r in results if r.get("similarity", 0) > 0.35]
            except Exception:
                pass

        # 5. Estructurar reporte asistido completo
        active_app = focused_win["app_class"] if focused_win else "Desktop Environment"
        active_title = focused_win["title"] if focused_win else "Escritorio General"

        report = f"🖥️ **Contexto Activo:** `{active_app}` — *{active_title}*\n"
        if monitors:
            mons_str = ", ".join([f"`{m['name']}` ({m['width']}x{m['height']})" for m in monitors])
            report += f"📺 **Monitores Detectados:** {mons_str}\n"
        report += f"📸 **Captura:** `{shot_path.name}`\n\n"
        
        report += "🔍 **Análisis de Pantalla & Acciones Sugeridas:**\n\n"
        report += visual_analysis + "\n\n"

        if rag_context:
            report += "💡 **Guía de Documentación Relevante (RAG Local):**\n"
            for chunk in rag_context:
                report += f"> {chunk[:250]}...\n\n"

        return {
            "success": True,
            "target": target,
            "screenshot_path": str(shot_path),
            "active_app": active_app,
            "active_title": active_title,
            "monitors": monitors,
            "windows_count": len(windows),
            "ocr_length": len(ocr_text),
            "report": report
        }

if __name__ == "__main__":
    engine = DesktopContextEngine()
    print("[+] Monitores conectados:", engine.list_monitors())
    print(f"[+] Ventanas detectadas ({len(engine.list_windows())}):")
    for w in engine.list_windows()[:5]:
        print(f"  - {'[*]' if w['is_focused'] else '[ ]'} [{w['app_class']}] {w['title']}")
