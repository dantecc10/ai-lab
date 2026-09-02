#!/usr/bin/env python3
"""
AI Lab — Creative Voice Generation Engine (Kokoro-82M Studio High-Fidelity)
Generador de voz creativa de alta expresividad, entonación natural y variedad de voces en CPU:
  - Síntesis de voz con Kokoro-82M en español, inglés y múltiples idiomas.
  - Catálogo de voces masculinas, femeninas, narradores y modulación de velocidad.
  - Mezcla e interpolación de voces (Voice Blending) para crear timbres únicos.
  - Exportación automática a WAV, MP3 y OGG Opus para notas de voz de Telegram.
"""

import os
import sys
import time
import tempfile
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List, Union

VOICES_OUTPUT_DIR = Path(os.path.expanduser("~/.local/share/ai-lab/voice_output"))
VOICES_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


class CreativeVoiceEngine:
    """Motor de síntesis vocal creativa y de alta fidelidad basado en Kokoro-82M."""

    VOICE_CATALOG = {
        # Voces en Español
        "ef_dora": {"name": "Dora", "lang": "e", "gender": "Femenino", "style": "Español Natural / Cálido", "desc": "Voz femenina expresiva y clara para narración y conversación."},
        "em_alex": {"name": "Alex", "lang": "e", "gender": "Masculino", "style": "Español Dinámico / Joven", "desc": "Voz masculina natural con entonación moderna."},
        "em_santa": {"name": "Santa", "lang": "e", "gender": "Masculino", "style": "Español Profundo / Grave", "desc": "Voz madura y profunda."},

        # Voces en Inglés Americano
        "af_bella": {"name": "Bella", "lang": "a", "gender": "Femenino", "style": "American Expressive", "desc": "Voz femenina ultra-expresiva y cinematográfica."},
        "af_sarah": {"name": "Sarah", "lang": "a", "gender": "Femenino", "style": "American Professional", "desc": "Voz institucional y serena."},
        "af_nicole": {"name": "Nicole", "lang": "a", "gender": "Femenino", "style": "American Casual", "desc": "Tono conversacional y relajado."},
        "am_adam": {"name": "Adam", "lang": "a", "gender": "Masculino", "style": "American Narrator", "desc": "Voz de locutor profesional y audiolibros."},
        "am_michael": {"name": "Michael", "lang": "a", "gender": "Masculino", "style": "American Friendly", "desc": "Voz masculina cercana y entusiasta."},
        "am_fenrir": {"name": "Fenrir", "lang": "a", "gender": "Masculino", "style": "American Cinematic Deep", "desc": "Voz épica, grave y cinematográfica."},

        # Voces en Inglés Británico
        "bf_emma": {"name": "Emma", "lang": "b", "gender": "Femenino", "style": "British Elegant", "desc": "Elegante y con acento refinado."},
        "bm_george": {"name": "George", "lang": "b", "gender": "Masculino", "style": "British Classic", "desc": "Locución clásica estilo BBC."}
    }

    def __init__(self):
        self._pipelines: Dict[str, Any] = {}

    def _get_pipeline(self, lang_code: str = "e"):
        """Inicializa o recupera el pipeline de Kokoro para el idioma solicitado fijado a CPU."""
        if lang_code not in self._pipelines:
            from kokoro import KPipeline
            self._pipelines[lang_code] = KPipeline(lang_code=lang_code, device="cpu")
        return self._pipelines[lang_code]

    def list_voices(self) -> List[Dict[str, Any]]:
        """Devuelve el catálogo de voces disponibles."""
        return [
            {"id": vid, **vinfo}
            for vid, vinfo in self.VOICE_CATALOG.items()
        ]

    DEFAULT_CONVERSATION_VOICE = "em_santa"
    DEFAULT_NOTIFICATION_VOICE = "bm_george"

    def synthesize(
        self,
        text: str,
        voice: str = "em_santa",
        speed: float = 1.0,
        output_format: str = "ogg"  # 'ogg', 'mp3', 'wav'
    ) -> Dict[str, Any]:
        """
        Sintetiza texto a voz con alta expresividad en CPU.
        Retorna la ruta del archivo generado y metadatos.
        """
        import soundfile as sf
        import numpy as np

        clean_text = text.replace("*", "").replace("`", "").replace("#", "").strip()
        if not clean_text:
            raise ValueError("El texto a sintetizar no puede estar vacío.")

        # Identificar idioma y configuración de voz
        voice_info = self.VOICE_CATALOG.get(voice)
        lang_code = voice_info["lang"] if voice_info else ("e" if voice.startswith("e") else "a")
        
        t0 = time.time()
        pipeline = self._get_pipeline(lang_code)

        # Generar segmentos de audio
        generator = pipeline(clean_text, voice=voice, speed=speed)
        audio_chunks = []

        for _, _, audio in generator:
            audio_chunks.append(audio)

        if not audio_chunks:
            raise RuntimeError("No se generó ningún segmento de audio.")

        full_audio = np.concatenate(audio_chunks)
        sample_rate = 24000
        duration_sec = round(len(full_audio) / sample_rate, 2)
        gen_time = round(time.time() - t0, 2)

        # Guardar archivo WAV temporal
        timestamp = int(time.time())
        base_name = f"voice_{voice}_{timestamp}"
        wav_path = VOICES_OUTPUT_DIR / f"{base_name}.wav"
        sf.write(str(wav_path), full_audio, sample_rate)

        # Conversión a formato final
        if output_format.lower() == "ogg":
            final_path = VOICES_OUTPUT_DIR / f"{base_name}.ogg"
            cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libopus", "-b:a", "48k", str(final_path)]
            subprocess.run(cmd, capture_output=True, check=True)
        elif output_format.lower() == "mp3":
            final_path = VOICES_OUTPUT_DIR / f"{base_name}.mp3"
            cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libmp3lame", "-b:a", "192k", str(final_path)]
            subprocess.run(cmd, capture_output=True, check=True)
        else:
            final_path = wav_path

        return {
            "file_path": str(final_path),
            "voice": voice,
            "voice_name": voice_info["name"] if voice_info else voice,
            "style": voice_info["style"] if voice_info else "Custom",
            "duration_sec": duration_sec,
            "gen_time_sec": gen_time,
            "sample_rate": sample_rate,
            "format": output_format
        }

    def mix_voices(
        self,
        voice_a: str,
        voice_b: str,
        weight_a: float = 0.5,
        text: str = "",
        speed: float = 1.0,
        output_format: str = "ogg"
    ) -> Dict[str, Any]:
        """Mezcla dos voces vectoriales para crear un nuevo timbre vocal único."""
        # En Kokoro, los tensores de voz se pueden promediar: voice_mix = weight_a * va + (1 - weight_a) * vb
        import torch
        from kokoro import KPipeline
        import soundfile as sf
        import numpy as np

        lang_code = "e" if voice_a.startswith("e") else "a"
        pipeline = self._get_pipeline(lang_code)
        
        # Cargar tensores de voz
        va = pipeline.load_voice(voice_a)
        vb = pipeline.load_voice(voice_b)
        
        # Interpolar pesos
        mixed_tensor = (weight_a * va) + ((1.0 - weight_a) * vb)

        t0 = time.time()
        generator = pipeline(text, voice=mixed_tensor, speed=speed)
        audio_chunks = [audio for _, _, audio in generator]

        full_audio = np.concatenate(audio_chunks)
        sample_rate = 24000
        duration_sec = round(len(full_audio) / sample_rate, 2)
        gen_time = round(time.time() - t0, 2)

        timestamp = int(time.time())
        base_name = f"voice_mix_{voice_a}_{voice_b}_{timestamp}"
        wav_path = VOICES_OUTPUT_DIR / f"{base_name}.wav"
        sf.write(str(wav_path), full_audio, sample_rate)

        final_path = VOICES_OUTPUT_DIR / f"{base_name}.ogg"
        cmd = ["ffmpeg", "-y", "-i", str(wav_path), "-c:a", "libopus", "-b:a", "48k", str(final_path)]
        subprocess.run(cmd, capture_output=True, check=True)

        return {
            "file_path": str(final_path),
            "voice": f"mix({voice_a}:{int(weight_a*100)}%, {voice_b}:{int((1-weight_a)*100)}%)",
            "duration_sec": duration_sec,
            "gen_time_sec": gen_time,
            "format": output_format
        }

    def speak_notification(
        self,
        message: str,
        voice: str = "bm_george",
        speed: float = 1.0,
        play_local: bool = True,
        visual_style: Optional[str] = "synthwave"
    ) -> Dict[str, Any]:
        """
        Sintetiza un mensaje de notificación y lo reproduce por los altavoces de la PC
        de forma asíncrona, opcionalmente activando una animación de teclado ASUS.
        """
        # Sintetizar audio en formato WAV para reproducción de baja latencia con paplay/pw-play
        synth_res = self.synthesize(text=message, voice=voice, speed=speed, output_format="wav")
        wav_file = synth_res["file_path"]

        # Lanzar aviso visual concurrente si está configurado
        if visual_style:
            try:
                from scripts.tools.visual_notifier import notifier
                import threading
                threading.Thread(
                    target=notifier.animate,
                    kwargs={"style": visual_style, "duration": min(max(synth_res["duration_sec"], 2.0), 8.0)},
                    daemon=True
                ).start()
            except Exception as e:
                print(f"[VisualAlert Warning]: {e}")

        # Reproducir localmente con paplay / pw-play
        if play_local and os.path.exists(wav_file):
            import threading
            def _play():
                player = "paplay" if subprocess.run(["which", "paplay"], capture_output=True).returncode == 0 else "pw-play"
                subprocess.run([player, wav_file], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)

            threading.Thread(target=_play, daemon=True).start()

        return {
            **synth_res,
            "played_locally": play_local,
            "visual_alert": visual_style
        }


# Singleton
creative_voice_engine = CreativeVoiceEngine()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_txt = " ".join(sys.argv[1:])
    else:
        test_txt = "Hola Dante. Este es el generador de voz creativa de alta fidelidad ejecutándose en CPU."
    
    print(f"Sintetizando: '{test_txt}'...")
    res = creative_voice_engine.synthesize(test_txt, voice="ef_dora")
    print(f"✅ Generado: {res['file_path']} ({res['duration_sec']}s en {res['gen_time_sec']}s)")
