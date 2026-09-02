#!/usr/bin/env python3
"""
AI Lab — Visual Alert, Dynamic Light Choreography & Color Animation Engine
Ofrece control total a la IA para componer animaciones visuales libres:
  - Paletas de múltiples colores y transiciones cromáticas
  - Animaciones temáticas (police, cyberpunk, matrix, rainbow, fire, aurora, heartbeat, breathe)
  - Keyframes personalizados con colores, brillos e intervalos en milisegundos
  - Presets de severidad (normal, important, critical, success)
  
SIEMPRE garantizando el retorno al color base del usuario: CIAN (#00ffff)
y al nivel de brillo original (ej: High).
"""

import os
import sys
import time
import shutil
import threading
import subprocess
from pathlib import Path
from typing import Optional, List, Dict, Any, Union

try:
    import asyncio
    from kasa import Discover
    KASA_AVAILABLE = True
except ImportError:
    KASA_AVAILABLE = False

BASE_CYAN_COLOR = "00ffff"

NAMED_COLORS = {
    "cyan": "00ffff",
    "blue": "0066ff",
    "ice": "00d4ff",
    "red": "ff0000",
    "crimson": "dc143c",
    "amber": "ffaa00",
    "gold": "ffd700",
    "orange": "ff5500",
    "green": "00ff66",
    "emerald": "00c853",
    "purple": "bf00ff",
    "violet": "7f00ff",
    "magenta": "ff007f",
    "pink": "ff69b4",
    "white": "ffffff",
    "yellow": "ffff00",
    "teal": "00e5ff",
}

THEME_ANIMATIONS = {
    "police": {
        "colors": ["ff0000", "0044ff"],
        "brightness": ["high", "off", "high", "off"],
        "speed": 0.08,
        "name": "Sirena Policial (Rojo / Azul)"
    },
    "siren": {
        "colors": ["ff0000", "0044ff"],
        "brightness": ["high", "off", "high", "off"],
        "speed": 0.08,
        "name": "Sirena (Rojo / Azul)"
    },
    "cyberpunk": {
        "colors": ["ff007f", "8800ff", "00ffff"],
        "brightness": ["high", "med", "high", "low"],
        "speed": 0.10,
        "name": "Cyberpunk Neon (Magenta / Púrpura / Cian)"
    },
    "synthwave": {
        "colors": ["ff0055", "7700ff", "00e5ff", "ffaa00"],
        "brightness": ["high", "med", "high", "low"],
        "speed": 0.12,
        "name": "Synthwave Glow"
    },
    "matrix": {
        "colors": ["00ff33", "008811", "00ff66"],
        "brightness": ["high", "low", "high", "off"],
        "speed": 0.09,
        "name": "Matrix Rain (Verdes)"
    },
    "rainbow": {
        "colors": ["ff0000", "ff7700", "ffff00", "00ff00", "00ffff", "0044ff", "aa00ff"],
        "brightness": ["high", "high", "high"],
        "speed": 0.15,
        "name": "Arcoíris Espectral (7 Colores)"
    },
    "fire": {
        "colors": ["ff2200", "ff6600", "ffaa00", "ff0000"],
        "brightness": ["high", "med", "high", "low"],
        "speed": 0.08,
        "name": "Llama / Fuego (Rojo / Naranja / Oro)"
    },
    "aurora": {
        "colors": ["00ffaa", "00aaff", "7700ff", "00e5ff"],
        "brightness": ["high", "med", "low", "med"],
        "speed": 0.18,
        "name": "Aurora Boreal (Turquesa / Violeta / Cian)"
    },
    "heartbeat": {
        "colors": ["ff0000", "ff0022", "880000"],
        "brightness": ["high", "low", "high", "off", "off"],
        "speed": 0.10,
        "name": "Latido de Corazón (Doble Pulso Rojo)"
    },
    "breathe": {
        "colors": ["00ffff", "0088ff"],
        "brightness": ["off", "low", "med", "high", "med", "low"],
        "speed": 0.20,
        "name": "Respiración Suave"
    },
    "strobe": {
        "colors": ["ffffff"],
        "brightness": ["high", "off", "high", "off"],
        "speed": 0.06,
        "name": "Estroboscópico Blanco Rápido"
    }
}


class VisualNotifier:
    """Motor de animación y efectos de iluminación dinámica para el teclado ASUS y lámpara."""

    def __init__(self, lamp_ip: str = "192.168.1.71", base_color: str = BASE_CYAN_COLOR):
        self.lamp_ip = lamp_ip
        self.base_color = base_color
        self.has_asusctl = bool(shutil.which("asusctl"))

    def resolve_color(self, color_str: str) -> str:
        """Convierte nombres de colores o hex en código hex limpio sin #."""
        c = color_str.lower().replace("#", "").strip()
        return NAMED_COLORS.get(c, c)

    def get_current_keyboard_brightness(self) -> str:
        """Obtiene el nivel de brillo actual del teclado (off, low, med, high)."""
        if not self.has_asusctl:
            return "high"
        try:
            res = subprocess.run(["asusctl", "leds", "get"], capture_output=True, text=True, timeout=2)
            out = res.stdout.lower()
            if "off" in out:
                return "off"
            elif "low" in out:
                return "low"
            elif "med" in out:
                return "med"
            elif "high" in out:
                return "high"
        except Exception:
            pass
        return "high"

    def set_color(self, hex_color: str):
        """Ajusta el color RGB estático en el teclado."""
        if not self.has_asusctl:
            return
        clean_hex = self.resolve_color(hex_color)
        try:
            subprocess.run(["asusctl", "aura", "effect", "static", "-c", clean_hex], capture_output=True, timeout=2)
        except Exception:
            pass

    def set_brightness(self, level: str):
        """Ajusta el nivel de brillo del teclado."""
        if not self.has_asusctl:
            return
        try:
            subprocess.run(["asusctl", "leds", "set", level], capture_output=True, timeout=2)
        except Exception:
            pass

    def restore_base_state(self, initial_brightness: str):
        """Restaura el color base (Cian #00ffff) y el brillo original."""
        self.set_color(self.base_color)
        self.set_brightness(initial_brightness)

    def _pulse_lamp(self, times: int = 1, delay: float = 0.4):
        """Hace parpadear la lámpara Lux si está disponible."""
        if not KASA_AVAILABLE:
            return

        async def _kasa_blink():
            try:
                plug = await Discover.discover_single(self.lamp_ip)
                await plug.update()
                orig_state = plug.is_on
                for _ in range(times):
                    if orig_state:
                        await plug.turn_off()
                        await asyncio.sleep(delay)
                        await plug.turn_on()
                        await asyncio.sleep(delay)
                    else:
                        await plug.turn_on()
                        await asyncio.sleep(delay)
                        await plug.turn_off()
                        await asyncio.sleep(delay)
            except Exception:
                pass

        try:
            asyncio.run(_kasa_blink())
        except Exception:
            pass

    def _execute_animation_loop(
        self,
        color_list: List[str],
        brightness_list: List[str],
        speed: float,
        duration_sec: float
    ):
        """Bucle de ejecución para animaciones basadas en listas de colores y brillos."""
        if not self.has_asusctl:
            return

        initial_brightness = self.get_current_keyboard_brightness()
        t_end = time.time() + duration_sec
        step = 0

        try:
            while time.time() < t_end:
                curr_color = color_list[step % len(color_list)]
                curr_bright = brightness_list[step % len(brightness_list)]
                
                self.set_color(curr_color)
                self.set_brightness(curr_bright)
                
                step += 1
                time.sleep(speed)
        finally:
            self.restore_base_state(initial_brightness)

    def _execute_keyframes(self, frames: List[Dict[str, Any]], duration_sec: float):
        """Ejecuta una secuencia personalizada de keyframes paso a paso."""
        if not self.has_asusctl:
            return

        initial_brightness = self.get_current_keyboard_brightness()
        t_end = time.time() + duration_sec

        try:
            while time.time() < t_end:
                for frame in frames:
                    if time.time() >= t_end:
                        break
                    c = frame.get("color")
                    b = frame.get("brightness")
                    delay_sec = frame.get("duration_ms", 100) / 1000.0

                    if c:
                        self.set_color(c)
                    if b:
                        self.set_brightness(b)
                    time.sleep(delay_sec)
        finally:
            self.restore_base_state(initial_brightness)

    def animate(
        self,
        style: Optional[str] = None,
        colors: Optional[Union[List[str], str]] = None,
        brightness_pattern: Optional[List[str]] = None,
        duration: Optional[float] = None,
        speed_ms: Optional[int] = None,
        frames: Optional[List[Dict[str, Any]]] = None,
        include_lamp: bool = False,
        level: Optional[str] = None
    ) -> str:
        """
        Punto de entrada principal con libertad creativa total para la IA.
        - style: 'police', 'cyberpunk', 'synthwave', 'matrix', 'rainbow', 'fire', 'aurora', 'heartbeat', 'breathe', 'strobe'
        - colors: Lista de colores hex o nombres (ej: ['red', 'blue', 'cyan'] o 'ff0000, 00ffff')
        - brightness_pattern: Lista de intensidades (ej: ['high', 'off', 'high', 'low'])
        - duration: Duración total en segundos (0.5 a 30s)
        - speed_ms: Intervalo entre pasos en milisegundos (ej: 80ms)
        - frames: Keyframes detallados [{'color': '...', 'brightness': '...', 'duration_ms': 100}]
        - level: Presets de severidad ('normal', 'important', 'critical', 'error', 'success')
        """
        # 1. Modo Keyframes
        if frames and isinstance(frames, list):
            dur = max(0.5, min(30.0, duration or 4.0))
            threading.Thread(target=self._execute_keyframes, args=(frames, dur), daemon=True).start()
            return f"🎬 Animación personalizada por keyframes iniciada ({dur:.1f}s) ➔ Retorno a Cian"

        # 2. Modo Estilos Temáticos (Theme Presets)
        style_key = (style or "").lower().strip()
        if style_key in THEME_ANIMATIONS:
            theme = THEME_ANIMATIONS[style_key]
            dur = max(0.5, min(30.0, duration or 4.0))
            color_list = [self.resolve_color(c) for c in (colors if colors else theme["colors"])]
            b_list = brightness_pattern if brightness_pattern else theme["brightness"]
            sp = (speed_ms / 1000.0) if speed_ms else theme["speed"]
            
            threading.Thread(
                target=self._execute_animation_loop,
                args=(color_list, b_list, sp, dur),
                daemon=True
            ).start()
            return f"🎨 Animación temática *{theme['name']}* ejecutándose ({dur:.1f}s) ➔ Retorno a Cian"

        # 3. Modo Multi-Color Libre
        if colors:
            if isinstance(colors, str):
                color_items = [c.strip() for c in colors.split(",") if c.strip()]
            else:
                color_items = colors
            color_list = [self.resolve_color(c) for c in color_items]
            dur = max(0.5, min(30.0, duration or 3.0))
            b_list = brightness_pattern if brightness_pattern else ["high", "low", "med", "high", "off"]
            sp = (speed_ms / 1000.0) if speed_ms else 0.12

            threading.Thread(
                target=self._execute_animation_loop,
                args=(color_list, b_list, sp, dur),
                daemon=True
            ).start()
            return f"✨ Animación multi-color ({', '.join(color_items)}) ejecutándose ({dur:.1f}s) ➔ Retorno a Cian"

        # 4. Modo Severidad / Nivel Estándar (Fallback a Presets de Notificación)
        lvl = (level or "normal").lower().strip()
        if lvl in ["critical", "error", "urgent"]:
            color_list = ["ff0000"]
            b_list = ["high", "off", "high", "low"]
            sp = (speed_ms / 1000.0) if speed_ms else 0.09
            dur = max(1.0, min(30.0, duration or 8.0))
            lamp_pulses = 2
            desc = "ROJO CRÍTICO"
        elif lvl in ["important", "warning", "warn"]:
            color_list = ["ffaa00"]
            b_list = ["high", "low", "high", "off"]
            sp = (speed_ms / 1000.0) if speed_ms else 0.11
            dur = max(1.0, min(30.0, duration or 4.0))
            lamp_pulses = 1
            desc = "ÁMBAR IMPORTANTE"
        elif lvl in ["success", "done"]:
            color_list = ["00ff66"]
            b_list = ["off", "low", "med", "high", "med"]
            sp = (speed_ms / 1000.0) if speed_ms else 0.13
            dur = max(1.0, min(30.0, duration or 2.5))
            lamp_pulses = 0
            desc = "VERDE ÉXITO"
        else:
            color_list = ["00f0ff"]
            b_list = ["off", "low", "med", "high", "low"]
            sp = (speed_ms / 1000.0) if speed_ms else 0.14
            dur = max(0.5, min(30.0, duration or 2.0))
            lamp_pulses = 1 if include_lamp and dur >= 2.5 else 0
            desc = "CIAN NORMAL"

        def _run_level_sequence():
            threads = [
                threading.Thread(target=self._execute_animation_loop, args=(color_list, b_list, sp, dur))
            ]
            if include_lamp and lamp_pulses > 0:
                threads.append(threading.Thread(target=self._pulse_lamp, args=(lamp_pulses, 0.4)))
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        threading.Thread(target=_run_level_sequence, daemon=True).start()
        return f"🔔 Aviso visual *{desc}* ({dur:.1f}s) ➔ Retorno a *CIAN Base (#00ffff)*"


# Instancia singleton
notifier = VisualNotifier()


def play_visual_alert(
    level: str = "normal",
    duration: Optional[float] = None,
    color: Optional[str] = None,
    style: Optional[str] = None,
    colors: Optional[Union[List[str], str]] = None,
    speed_ms: Optional[int] = None,
    include_lamp: bool = False
) -> str:
    """Función de acceso directo para la IA."""
    if style or colors:
        return notifier.animate(style=style, colors=colors or color, duration=duration, speed_ms=speed_ms, include_lamp=include_lamp)
    return notifier.animate(level=level, colors=color, duration=duration, speed_ms=speed_ms, include_lamp=include_lamp)


if __name__ == "__main__":
    test_style = sys.argv[1] if len(sys.argv) > 1 else "police"
    test_dur = float(sys.argv[2]) if len(sys.argv) > 2 else 3.0
    print(f"Probando animación '{test_style}' durante {test_dur}s...")
    res = notifier.animate(style=test_style, duration=test_dur)
    print(res)
    time.sleep(test_dur + 0.5)
    print("Prueba completada. Teclado restaurado a Cian (#00ffff).")
