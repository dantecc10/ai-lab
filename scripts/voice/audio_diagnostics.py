#!/usr/bin/env python3
"""
AI Lab — Audio Diagnostics & Volume Health Monitor
Diagnostica el volumen del sistema, estado de mute en PipeWire/PulseAudio
y emite alertas si el volumen es insuficiente para la conversación por voz.
"""

import os
import re
import shutil
import subprocess
from typing import Tuple

class AudioDiagnostics:
    """Diagnóstico y control del subsistema de audio y volumen."""

    @staticmethod
    def get_output_volume() -> dict:
        """Obtiene el volumen actual y estado de mute del sumidero de audio por defecto."""
        # 1. Intentar con pactl
        if shutil.which("pactl"):
            try:
                # Obtener volumen
                vol_res = subprocess.run(
                    ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                    capture_output=True, text=True, timeout=2.0
                )
                mute_res = subprocess.run(
                    ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                    capture_output=True, text=True, timeout=2.0
                )
                
                vol_match = re.search(r"(\d+)%", vol_res.stdout)
                vol_percent = int(vol_match.group(1)) if vol_match else 100
                is_muted = "yes" in mute_res.stdout.lower()

                return {
                    "available": True,
                    "volume_percent": vol_percent,
                    "is_muted": is_muted,
                    "backend": "pactl"
                }
            except Exception:
                pass

        # 2. Fallback con wpctl (PipeWire)
        if shutil.which("wpctl"):
            try:
                res = subprocess.run(
                    ["wpctl", "get-volume", "@DEFAULT_AUDIO_SINK@"],
                    capture_output=True, text=True, timeout=2.0
                )
                # Formato: "Volume: 0.85 [MUTED]" o "Volume: 0.85"
                out = res.stdout.strip()
                is_muted = "[MUTED]" in out
                vol_match = re.search(r"Volume:\s+([\d\.]+)", out)
                vol_percent = int(float(vol_match.group(1)) * 100) if vol_match else 100

                return {
                    "available": True,
                    "volume_percent": vol_percent,
                    "is_muted": is_muted,
                    "backend": "wpctl"
                }
            except Exception:
                pass

        # 3. Fallback con amixer
        if shutil.which("amixer"):
            try:
                res = subprocess.run(
                    ["amixer", "get", "Master"],
                    capture_output=True, text=True, timeout=2.0
                )
                vol_match = re.search(r"\[(\d+)%\]", res.stdout)
                vol_percent = int(vol_match.group(1)) if vol_match else 100
                is_muted = "[off]" in res.stdout

                return {
                    "available": True,
                    "volume_percent": vol_percent,
                    "is_muted": is_muted,
                    "backend": "amixer"
                }
            except Exception:
                pass

        return {
            "available": False,
            "volume_percent": 100,
            "is_muted": False,
            "backend": "none"
        }

    @classmethod
    def check_audibility(cls, min_volume: int = 15, notify_if_inaudible: bool = True) -> Tuple[bool, str]:
        """Comprueba si el audio es audible para la respuesta por voz y notifica si no."""
        info = cls.get_output_volume()
        if not info["available"]:
            return True, "No se pudo consultar el control de volumen."

        if info["is_muted"]:
            msg = "⚠️ Las bocinas del sistema están silenciadas (Mute activo)."
            if notify_if_inaudible and shutil.which("notify-send"):
                try:
                    subprocess.run(
                        ["notify-send", "-a", "AI Voice", "-t", "4000", "⚠️ Audio Silenciado",
                         "El asistente respondió por voz pero las bocinas están muteadas."],
                        check=False
                    )
                except Exception:
                    pass
            return False, msg

        if info["volume_percent"] < min_volume:
            msg = f"⚠️ El volumen del sistema está muy bajo ({info['volume_percent']}% < {min_volume}%)."
            if notify_if_inaudible and shutil.which("notify-send"):
                try:
                    subprocess.run(
                        ["notify-send", "-a", "AI Voice", "-t", "4000", "⚠️ Volumen Muy Bajo",
                         f"Volumen actual al {info['volume_percent']}%. Podrías no escuchar la respuesta."],
                        check=False
                    )
                except Exception:
                    pass
            return False, msg

        return True, f"Volumen adecuado ({info['volume_percent']}%)."

    @classmethod
    def set_volume(cls, percent: int, unmute: bool = True) -> dict:
        """Ajusta el volumen del sistema y desactiva el mute."""
        percent = max(0, min(150, percent))
        
        if shutil.which("pactl"):
            try:
                subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"], check=False)
                if unmute:
                    subprocess.run(["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"], check=False)
                return {"success": True, "volume_percent": percent, "unmuted": unmute, "backend": "pactl"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        if shutil.which("amixer"):
            try:
                subprocess.run(["amixer", "set", "Master", f"{percent}%"], check=False)
                if unmute:
                    subprocess.run(["amixer", "set", "Master", "unmute"], check=False)
                return {"success": True, "volume_percent": percent, "unmuted": unmute, "backend": "amixer"}
            except Exception as e:
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "No se encontró control de volumen (pactl o amixer)."}

    @classmethod
    def get_input_volume(cls) -> dict:
        """Obtiene el volumen y estado del micrófono por defecto."""
        if shutil.which("pactl"):
            try:
                vol_res = subprocess.run(["pactl", "get-source-volume", "@DEFAULT_SOURCE@"], capture_output=True, text=True, timeout=2.0)
                mute_res = subprocess.run(["pactl", "get-source-mute", "@DEFAULT_SOURCE@"], capture_output=True, text=True, timeout=2.0)
                vol_match = re.search(r"(\d+)%", vol_res.stdout)
                vol_percent = int(vol_match.group(1)) if vol_match else 100
                is_muted = "yes" in mute_res.stdout.lower()
                return {"available": True, "volume_percent": vol_percent, "is_muted": is_muted, "backend": "pactl"}
            except Exception:
                pass
        return {"available": False, "volume_percent": 80, "is_muted": False, "backend": "none"}

    @classmethod
    def ensure_microphone_gain(cls, target_percent: int = 85) -> bool:
        """Asegura que el micrófono no esté silenciado y tenga ganancia adecuada (>=75%)."""
        if shutil.which("pactl"):
            try:
                inp = cls.get_input_volume()
                if inp["is_muted"]:
                    subprocess.run(["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "0"], check=False)
                if inp["volume_percent"] < 70:
                    subprocess.run(["pactl", "set-source-volume", "@DEFAULT_SOURCE@", f"{target_percent}%"], check=False)
                return True
            except Exception:
                pass
        return False

if __name__ == "__main__":
    diag = AudioDiagnostics()
    print("[+] Diagnóstico de audio del sistema:")
    vol = diag.get_output_volume()
    print(f"• Volumen actual: {vol['volume_percent']}% | Muted: {vol['is_muted']} (Backend: {vol['backend']})")
    audible, reason = diag.check_audibility()
    print(f"• ¿Audible?: {audible} -> {reason}")
