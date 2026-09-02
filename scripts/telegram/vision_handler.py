"""
AI Lab — Telegram Bot Multimodal Vision & OCR Handler
Procesa imágenes, fotos y documentos enviados por Telegram utilizando OCR local y el motor multimodal.
"""

import os
import sys
from pathlib import Path

# Inyectar ai-lab root en sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from scripts.vision.multimodal_vision import MultimodalVisionEngine
except ImportError:
    MultimodalVisionEngine = None


class VisionHandler:
    """Manejador de análisis visual, OCR y multimodal para Telegram."""

    def __init__(self, media_dir: str | Path | None = None):
        self.media_dir = Path(media_dir or (Path.home() / ".local" / "share" / "ai-lab" / "media")).resolve()
        self.media_dir.mkdir(parents=True, exist_ok=True)
        if MultimodalVisionEngine:
            self.engine = MultimodalVisionEngine()
        else:
            self.engine = None

    def process_image(self, image_path: Path, user_prompt: str = "") -> dict:
        """Analiza la imagen recibida mediante visión multimodal y OCR."""
        p = Path(image_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Imagen no encontrada en {p}")

        prompt = user_prompt.strip() or "Describe detalladamente esta imagen, identifica texto, diagramas, objetos o errores visibles y resume la información clave."

        if self.engine:
            try:
                analysis = self.engine.analyze_image(p, prompt=prompt)
                ocr_text = self.engine.run_ocr(p)
                return {
                    "path": str(p),
                    "filename": p.name,
                    "analysis": analysis,
                    "ocr": ocr_text,
                    "summary": f"🖼️ [Imagen recibida: {p.name}]\n\n{analysis}"
                }
            except Exception as e:
                print(f"[Vision Engine Error]: {e}")

        # Fallback si no hay motor multimodal disponible
        return {
            "path": str(p),
            "filename": p.name,
            "analysis": f"Imagen guardada en {p}",
            "ocr": "",
            "summary": f"🖼️ [Imagen recibida y almacenada en {p.name}]"
        }

    def capture_desktop_screenshot(self) -> Path:
        """Toma una captura de pantalla del escritorio de la máquina local."""
        if not self.engine:
            raise RuntimeError("Motor de visión no inicializado.")
        return self.engine.capture_screen()
