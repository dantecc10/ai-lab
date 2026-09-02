#!/usr/bin/env python3
"""
AI Lab — Voice Profiles & Multilingual Accent Customizer
Gestiona perfiles de voz, idiomas, acentos, velocidad y tono configurables.
"""

import os
import sys
import json
import configparser
from pathlib import Path

DEFAULT_CONFIG_PATH = Path.home() / ".config" / "ai-lab" / "voice-profile.conf"
REPO_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "configs" / "voice-profile.conf"

DEFAULT_PROFILES = {
    "es_MX_alvaro": {
        "name": "Álvaro (Español México)",
        "language": "es-MX",
        "engine": "piper",
        "model": "es_MX-ald-medium.onnx",
        "spd_voice": "female1",
        "speed": 1.0,
        "pitch": 1.0
    },
    "es_ES_castilian": {
        "name": "Castellano (España)",
        "language": "es-ES",
        "engine": "spd-say",
        "spd_voice": "male1",
        "speed": 1.0,
        "pitch": 0.95
    },
    "en_US_natural": {
        "name": "Natural (English US)",
        "language": "en-US",
        "engine": "spd-say",
        "spd_voice": "female1",
        "speed": 1.05,
        "pitch": 1.0
    },
    "en_GB_british": {
        "name": "George (English British)",
        "language": "en-GB",
        "engine": "spd-say",
        "spd_voice": "male2",
        "speed": 0.95,
        "pitch": 1.05
    },
    "fast_assistant": {
        "name": "Asistente Rápido (1.25x)",
        "language": "es-MX",
        "engine": "auto",
        "speed": 1.25,
        "pitch": 1.0
    }
}

class VoiceProfileManager:
    """Administrador de perfiles de voz y configuración fonética."""

    def __init__(self, config_path: Path | None = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.config_path.exists() and REPO_CONFIG_PATH.exists():
            import shutil
            shutil.copy2(REPO_CONFIG_PATH, self.config_path)

    def get_active_profile(self) -> dict:
        """Devuelve la configuración del perfil activo con overrides de velocidad y tono."""
        config = configparser.ConfigParser()
        if self.config_path.exists():
            config.read(self.config_path)

        profile_id = config.get("active", "profile", fallback="es_MX_alvaro")
        base = DEFAULT_PROFILES.get(profile_id, DEFAULT_PROFILES["es_MX_alvaro"]).copy()

        # Overrides desde sección [active]
        base["profile_id"] = profile_id
        base["language"] = config.get("active", "language", fallback=base.get("language", "es-MX"))
        base["speed"] = config.getfloat("active", "speed", fallback=float(base.get("speed", 1.0)))
        base["pitch"] = config.getfloat("active", "pitch", fallback=float(base.get("pitch", 1.0)))
        base["volume"] = config.getint("active", "volume", fallback=100)
        base["engine"] = config.get("active", "engine", fallback=base.get("engine", "auto"))

        return base

    def set_profile(self, profile_id: str, language: str | None = None, speed: float | None = None,
                    pitch: float | None = None, volume: int | None = None) -> dict:
        """Actualiza el perfil activo o ajusta parámetros de velocidad/tono."""
        if profile_id not in DEFAULT_PROFILES and profile_id != "custom":
            raise ValueError(f"Perfil '{profile_id}' no válido. Opciones: {list(DEFAULT_PROFILES.keys())}")

        config = configparser.ConfigParser()
        if self.config_path.exists():
            config.read(self.config_path)

        if "active" not in config:
            config["active"] = {}

        config["active"]["profile"] = profile_id
        if language:
            config["active"]["language"] = language
        if speed is not None:
            config["active"]["speed"] = str(round(max(0.5, min(2.5, speed)), 2))
        if pitch is not None:
            config["active"]["pitch"] = str(round(max(0.5, min(2.0, pitch)), 2))
        if volume is not None:
            config["active"]["volume"] = str(max(10, min(150, volume)))

        with open(self.config_path, "w", encoding="utf-8") as f:
            config.write(f)

        return self.get_active_profile()

    def list_available_profiles(self) -> list[dict]:
        """Lista todos los perfiles disponibles."""
        active = self.get_active_profile()
        result = []
        for pid, pdata in DEFAULT_PROFILES.items():
            entry = pdata.copy()
            entry["id"] = pid
            entry["is_active"] = (pid == active["profile_id"])
            result.append(entry)
        return result

if __name__ == "__main__":
    mgr = VoiceProfileManager()
    print("[+] Perfil de voz activo:", mgr.get_active_profile())
    print("[+] Perfiles disponibles:", [p["name"] for p in mgr.list_available_profiles()])
