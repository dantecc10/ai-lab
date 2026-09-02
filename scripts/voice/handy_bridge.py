#!/usr/bin/env python3
"""
AI Lab — Handy (cjpais/Handy) Integration Bridge
Conecta el ecosistema de AI Lab con la aplicación Handy y el modelo Parakeet V3 (NVIDIA NeMo).
"""

import os
import re
import sys
import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

HANDY_LOG_PATH = Path.home() / ".local" / "share" / "com.pais.handy" / "logs" / "handy.log"
HANDY_RECORDINGS_DIR = Path.home() / ".local" / "share" / "com.pais.handy" / "recordings"

class HandyBridge:
    """Puente de integración bidireccional con la aplicación Handy."""

    def __init__(self):
        self.bin_path = shutil.which("handy") or "/usr/bin/handy"
        self.available = Path(self.bin_path).exists()

    def is_daemon_running(self) -> bool:
        """Verifica si la instancia GUI o demonio de Handy está en ejecución."""
        try:
            res = subprocess.run(["pgrep", "-f", "/usr/bin/handy"], capture_output=True, text=True)
            return res.returncode == 0
        except Exception:
            return False

    def toggle_transcription(self) -> Dict[str, Any]:
        """Envía la señal a Handy para iniciar o detener la grabación/transcripción."""
        if not self.available:
            return {"success": False, "error": "Handy binary not found."}
        try:
            res = subprocess.run([self.bin_path, "--toggle-transcription"], capture_output=True, text=True, timeout=3.0)
            return {
                "success": res.returncode == 0,
                "output": res.stdout.strip(),
                "error": res.stderr.strip() if res.returncode != 0 else None
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    def cancel_transcription(self) -> Dict[str, Any]:
        """Cancela la operación actual en Handy."""
        if not self.available:
            return {"success": False, "error": "Handy binary not found."}
        try:
            res = subprocess.run([self.bin_path, "--cancel"], capture_output=True, text=True, timeout=3.0)
            return {"success": res.returncode == 0}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_latest_transcription(self) -> Optional[Dict[str, Any]]:
        """Extrae la última transcripción registrada en los logs de Handy."""
        if not HANDY_LOG_PATH.exists():
            return None

        try:
            lines = HANDY_LOG_PATH.read_text(encoding="utf-8", errors="ignore").splitlines()
            # Buscar desde el final hacia el principio
            for line in reversed(lines):
                if "Transcription result:" in line or "Transcription completed in" in line:
                    match = re.search(r"Transcription result:\s*(.*)", line)
                    if match:
                        text = match.group(1).strip()
                        return {
                            "text": text,
                            "raw_log": line
                        }
        except Exception:
            pass
        return None

    def get_latest_recording_file(self) -> Optional[Path]:
        """Devuelve la ruta al archivo WAV grabado más reciente de Handy."""
        if not HANDY_RECORDINGS_DIR.exists():
            return None
        try:
            wavs = list(HANDY_RECORDINGS_DIR.glob("*.wav"))
            if wavs:
                return max(wavs, key=lambda p: p.stat().st_mtime)
        except Exception:
            pass
        return None

    def get_status(self) -> Dict[str, Any]:
        """Obtiene el estado general de la integración con Handy."""
        from scripts.voice.parakeet_engine import ParakeetEngine
        parakeet = ParakeetEngine()
        latest = self.get_latest_transcription()
        latest_file = self.get_latest_recording_file()

        return {
            "handy_installed": self.available,
            "daemon_running": self.is_daemon_running(),
            "parakeet_v3_ready": parakeet.available,
            "latest_transcript": latest.get("text") if latest else None,
            "latest_recording": str(latest_file) if latest_file else None
        }

if __name__ == "__main__":
    bridge = HandyBridge()
    print("[+] Estado de integración Handy:")
    print(json.dumps(bridge.get_status(), indent=2, ensure_ascii=False))
