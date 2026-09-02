import os
import mimetypes
from pathlib import Path
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

router = APIRouter()

# Extensiones multimedia permitidas
ALLOWED_EXTENSIONS = {
    # Imágenes
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico", ".tiff",
    # Audio
    ".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus",
    # Video
    ".mp4", ".webm", ".mov", ".mkv", ".avi",
    # Documentos
    ".pdf", ".txt", ".json", ".md"
}


@router.get("/media")
async def get_local_media(path: str = Query(..., description="Ruta absoluta o relativa del archivo local")):
    """Sirve archivos multimedia locales (imágenes, audio, video) para renderizarlos en la interfaz web de chat."""
    # Expandir ~ si es necesario
    if path.startswith("~"):
        path = os.path.expanduser(path)

    file_path = Path(path).resolve()

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"Archivo no encontrado: {path}")

    if not file_path.is_file():
        raise HTTPException(status_code=400, detail=f"La ruta no es un archivo: {path}")

    ext = file_path.suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=403, detail=f"Tipo de archivo no permitido para visualización: {ext}")

    mime_type, _ = mimetypes.guess_type(str(file_path))
    if not mime_type:
        mime_type = "application/octet-stream"

    return FileResponse(
        path=str(file_path),
        media_type=mime_type,
        filename=file_path.name,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, HEAD, OPTIONS",
            "Access-Control-Allow-Headers": "*",
            "Cross-Origin-Resource-Policy": "cross-origin",
            "Cross-Origin-Embedder-Policy": "credentialless",
            "Cache-Control": "public, max-age=3600"
        }
    )
