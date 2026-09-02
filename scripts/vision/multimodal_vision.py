#!/usr/bin/env python3
"""
AI Lab — Local Multimodal Vision & OCR Engine
Procesa imágenes locales, capturas de pantalla de escritorio y documentos mediante
inferencia visual (Gemma 4 Multimodal / llama.cpp) y OCR local (Tesseract).
"""

import os
import sys
import time
import json
import base64
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

# Asegurar que la raíz del proyecto ai-lab esté en sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

MEDIA_DIR = Path.home() / ".local" / "share" / "ai-lab" / "media"
LLAMA_ENDPOINT = "http://127.0.0.1:9090/v1/chat/completions"

class MultimodalVisionEngine:
    """Motor de visión multimodal e inspección visual local."""

    def __init__(self, endpoint: str = LLAMA_ENDPOINT):
        self.endpoint = endpoint
        MEDIA_DIR.mkdir(parents=True, exist_ok=True)

    def capture_screen(self, filename: str | None = None) -> Path:
        """Captura la pantalla completa del escritorio y la guarda en la carpeta multimedia."""
        fname = filename or f"screenshot_desktop_{int(time.time())}.png"
        if not fname.endswith(".png"):
            fname += ".png"
        out_path = MEDIA_DIR / fname

        env = os.environ.copy()
        if "DISPLAY" not in env:
            env["DISPLAY"] = ":0"

        # 1. Intentar cosmic-screenshot (Pop!_OS COSMIC Wayland nativo)
        if shutil.which("cosmic-screenshot"):
            try:
                res = subprocess.run([
                    "cosmic-screenshot",
                    "--interactive=false",
                    "--notify=false",
                    "--save-dir", str(out_path.parent)
                ], capture_output=True, text=True, timeout=5.0)
                out_file = res.stdout.strip()
                if out_file and os.path.exists(out_file):
                    if out_file != str(out_path):
                        shutil.move(out_file, str(out_path))
                    return out_path
                import glob
                pngs = sorted(glob.glob(str(out_path.parent / "Screenshot_*.png")), key=os.path.getmtime, reverse=True)
                if pngs and os.path.exists(pngs[0]):
                    if pngs[0] != str(out_path):
                        shutil.move(pngs[0], str(out_path))
                    return out_path
            except Exception:
                pass

        # 2. Fallback a maim (X11 / XWayland)
        if shutil.which("maim"):
            try:
                res = subprocess.run(["maim", str(out_path)], env=env, capture_output=True, timeout=3.0)
                if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                    return out_path
            except Exception:
                pass

        # 3. Fallback a ImageMagick import con timeout
        if shutil.which("import"):
            try:
                res = subprocess.run(["import", "-window", "root", str(out_path)], env=env, capture_output=True, timeout=3.0)
                if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                    return out_path
            except Exception:
                pass

        # 4. Fallback a gnome-screenshot
        if shutil.which("gnome-screenshot"):
            try:
                res = subprocess.run(["gnome-screenshot", "-f", str(out_path)], env=env, capture_output=True, timeout=3.0)
                if res.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
                    return out_path
            except Exception:
                pass

        # 5. Fallback a BrowserEngine screenshot si la sesión de escritorio está bloqueada/headless
        try:
            from scripts.tools.browser_engine import BrowserEngine
            engine = BrowserEngine()
            ss = engine.screenshot(name=fname)
            if Path(ss["file_path"]).exists():
                return Path(ss["file_path"])
        except Exception:
            pass

        raise RuntimeError("No se pudo capturar la pantalla (servidor X11/Wayland o navegador no accesibles).")

    def run_ocr(self, image_path: Path | str) -> str:
        """Extrae el texto de la imagen mediante Tesseract OCR local."""
        p = Path(image_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Imagen no encontrada en {p}")

        if not shutil.which("tesseract"):
            return "(Tesseract OCR no instalado en el sistema)"

        res = subprocess.run(
            ["tesseract", str(p), "stdout", "-l", "spa+eng"],
            capture_output=True,
            text=True
        )
        if res.returncode != 0:
            # Reintentar sin especificar idioma si falta el paquete de idioma
            res = subprocess.run(["tesseract", str(p), "stdout"], capture_output=True, text=True)

        return res.stdout.strip()

    def analyze_image(self, image_path: Path | str, prompt: str = "Describe esta imagen en detalle y extrae la información relevante.") -> str:
        """Analiza la imagen utilizando la API multimodal de llama.cpp (o fallback OCR + metadata)."""
        p = Path(image_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Imagen no encontrada en {p}")

        img_bytes = p.read_bytes()
        b64_img = base64.b64encode(img_bytes).decode("utf-8")
        ext = p.suffix.lower().lstrip(".") or "png"
        if ext == "jpg":
            ext = "jpeg"
        mime_type = f"image/{ext}"

        # 1. Intentar inferencia visual con llama-server (OpenAI format)
        payload = {
            "model": "default",
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{b64_img}"
                            }
                        }
                    ]
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.3
        }

        try:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                reply = data["choices"][0]["message"]["content"]
                return reply
        except Exception:
            # Si el modelo activo en llama-server no soporta visión directa, aplicar OCR + análisis de metadatos
            ocr_text = self.run_ocr(p)
            file_size_kb = len(img_bytes) / 1024.0
            
            result = f"🖼️ **Análisis Visual (OCR & Metadatos):**\n\n"
            result += f"• **Archivo**: `{p.name}` ({file_size_kb:.1f} KB)\n"
            result += f"• **Ruta**: `{p}`\n\n"
            if ocr_text:
                result += f"📝 **Texto Detectado en la Imagen (OCR):**\n```\n{ocr_text}\n```"
            else:
                result += "ℹ️ *No se detectó texto legible en la imagen.*"
            return result

    def inspect_screen(self, prompt: str = "Analiza el contenido de la pantalla y describe la actividad actual.") -> dict:
        """Captura la pantalla actual y ejecuta el análisis visual."""
        shot_path = self.capture_screen()
        analysis = self.analyze_image(shot_path, prompt=prompt)
        return {
            "screenshot_path": str(shot_path),
            "filename": shot_path.name,
            "analysis": analysis
        }

if __name__ == "__main__":
    engine = MultimodalVisionEngine()
    print("[+] MultimodalVisionEngine inicializado.")
    try:
        shot = engine.capture_screen("test_multimodal_screen.png")
        print(f"[✓] Captura realizada en: {shot}")
        ocr = engine.run_ocr(shot)
        print(f"[✓] OCR extraído: {len(ocr)} caracteres")
    except Exception as e:
        print(f"[!] Error de prueba: {e}")
