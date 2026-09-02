#!/usr/bin/env python3
"""
AI Lab — NVIDIA NeMo Parakeet TDT V3 ASR Engine (vía Handy CLI & ONNX)
Transcriptor ultrarrápido (12x tiempo real en CPU) y de alta precisión para español.
"""

import os
import sys
import json
import shutil
import subprocess
from pathlib import Path

HANDY_BIN = shutil.which("handy") or "/usr/bin/handy"
PARAKEET_MODEL_ID = "parakeet-tdt-0.6b-v3"
PARAKEET_LOCAL_DIR = Path.home() / ".local" / "share" / "com.pais.handy" / "models" / "parakeet-tdt-0.6b-v3-int8"

class ParakeetEngine:
    """Motor de transcripción por voz NVIDIA Parakeet TDT V3."""

    def __init__(self, model_id: str = PARAKEET_MODEL_ID):
        self.model_id = model_id
        self.available = Path(HANDY_BIN).exists() and (PARAKEET_LOCAL_DIR.exists() or self.is_model_installed())

    def is_model_installed(self) -> bool:
        """Comprueba si el modelo Parakeet V3 está instalado en Handy."""
        if not Path(HANDY_BIN).exists():
            return False
        try:
            res = subprocess.run([HANDY_BIN, "--list-models", "--json"], capture_output=True, text=True, timeout=5.0)
            if res.returncode == 0:
                models = json.loads(res.stdout)
                return any(m.get("id") == self.model_id and m.get("is_downloaded") for m in models)
        except Exception:
            pass
        return False

    def transcribe(self, wav_path: Path | str) -> dict:
        """Transcribe un archivo WAV a 16kHz mono usando Parakeet V3."""
        p = Path(wav_path).expanduser().resolve()
        if not p.exists():
            raise FileNotFoundError(f"Archivo de audio no encontrado: {p}")

        if not self.available:
            raise RuntimeError("Parakeet V3 / Handy no está disponible en el sistema.")

        try:
            cmd = [
                HANDY_BIN,
                "-f", str(p),
                "--model", self.model_id,
                "--json"
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15.0)
            
            # La salida JSON se encuentra al final de stdout
            stdout_lines = res.stdout.strip().splitlines()
            json_line = next((line for line in reversed(stdout_lines) if line.startswith("{") and line.endswith("}")), None)
            
            if json_line:
                data = json.loads(json_line)
                return {
                    "success": True,
                    "text": data.get("text", "").strip(),
                    "duration_sec": data.get("audio_secs", 0.0),
                    "latency_ms": data.get("best_ms") or (data.get("transcribe_ms", [0])[0] if data.get("transcribe_ms") else 0),
                    "rtf": data.get("rtf", 0.0),
                    "engine": "parakeet_tdt_v3"
                }
            elif res.returncode == 0:
                # Fallback de parseo de texto directo
                return {
                    "success": True,
                    "text": res.stdout.strip(),
                    "engine": "parakeet_tdt_v3"
                }
            else:
                return {
                    "success": False,
                    "text": "",
                    "error": res.stderr.strip() or "Error al ejecutar Handy CLI."
                }
        except Exception as e:
            return {"success": False, "text": "", "error": str(e)}

if __name__ == "__main__":
    engine = ParakeetEngine()
    print(f"[+] Parakeet V3 Disponible: {engine.available}")
    test_audio = Path.home() / ".local" / "share" / "com.pais.handy" / "recordings" / "handy-1788168551.wav"
    if test_audio.exists():
        print("[+] Probando transcripción de muestra:")
        res = engine.transcribe(test_audio)
        print(f"• Texto: '{res.get('text')}' (Latencia: {res.get('latency_ms')}ms, RTF: {res.get('rtf'):.1f}x)")
