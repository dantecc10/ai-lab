"""
AI Lab — Telegram Bot Voice & Audio Handler
Procesa notas de voz entrantes (Speech-to-Text con Whisper) y síntesis de respuestas (TTS con Piper/ffmpeg).
"""

import os
import sys
import subprocess
import tempfile
import urllib.request
import json
from pathlib import Path

# Añadir venv si existe
skills_venv = os.path.expanduser("~/scripting/gpu-tools/skills/.venv/lib/python3.12/site-packages")
if os.path.exists(skills_venv) and skills_venv not in sys.path:
    sys.path.insert(0, skills_venv)


class VoiceHandler:
    """Manejador de audio, STT y TTS para Telegram."""

    def __init__(self, whisper_url: str = "http://127.0.0.1:9093/v1/audio/transcriptions"):
        self.whisper_url = whisper_url
        self.temp_dir = Path(tempfile.gettempdir()) / "ai_lab_telegram_voice"
        self.temp_dir.mkdir(parents=True, exist_ok=True)

    def convert_to_wav(self, input_audio: Path) -> Path:
        """Convierte cualquier formato de audio de Telegram (.oga, .ogg, .mp3, etc.) a WAV 16kHz mono."""
        output_wav = self.temp_dir / f"{input_audio.stem}_16k.wav"
        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_audio),
            "-ar", "16000",
            "-ac", "1",
            "-c:a", "pcm_s16le",
            str(output_wav)
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Error al convertir audio con ffmpeg: {res.stderr}")
        return output_wav

    def transcribe(self, audio_path: Path) -> str:
        """Transcribe un archivo de audio utilizando el servidor local de Whisper."""
        p = Path(audio_path).resolve()
        if not p.exists():
            raise FileNotFoundError(f"Archivo de audio no encontrado: {p}")

        # Convertir a WAV primero para asegurar compatibilidad total
        wav_path = self.convert_to_wav(p)

        # 1. Intentar petición HTTP a Whisper Server (Puerto 9093)
        try:
            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            with open(wav_path, "rb") as f:
                file_content = f.read()

            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{wav_path.name}"\r\n'
                f"Content-Type: audio/wav\r\n\r\n"
            ).encode("utf-8") + file_content + f"\r\n--{boundary}\r\n" \
                f'Content-Disposition: form-data; name="model"\r\n\r\n' \
                f"whisper-base\r\n--{boundary}--\r\n".encode("utf-8")

            req = urllib.request.Request(
                self.whisper_url,
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=45.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                text = data.get("text", "").strip()
                if text:
                    return text
        except Exception as e:
            print(f"[Whisper Server Fallback]: {e}")

        # 2. Fallback: faster-whisper local directo
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("small", device="cpu", compute_type="int8", cpu_threads=4)
            segments, _ = model.transcribe(str(wav_path), language="es", vad_filter=True)
            text = " ".join([s.text for s in segments]).strip()
            if text:
                return text
        except Exception as e:
            print(f"[Whisper Local Fallback Error]: {e}")

        raise RuntimeError("No se pudo transcribir el audio (el servidor Whisper no respondió).")

    def synthesize(self, text: str, output_name: str | None = None) -> Path | None:
        """Sintetiza texto a voz y genera un archivo de audio OGG (Opus) para Telegram."""
        if not text.strip():
            return None

        clean_text = text.replace("*", "").replace("`", "").replace("#", "").strip()
        # Limitar longitud para notas de voz
        if len(clean_text) > 1000:
            clean_text = clean_text[:997] + "..."

        out_name = output_name or f"voice_reply_{int(tempfile._get_candidate_names().__next__(), 36)}.ogg"
        out_ogg = self.temp_dir / out_name
        temp_wav = self.temp_dir / f"{out_ogg.stem}.wav"

        # 1. Usar motor de voz creativa de alta fidelidad Kokoro-82M (em_santa)
        try:
            from scripts.voice.creative_voice_engine import creative_voice_engine
            res = creative_voice_engine.synthesize(clean_text, voice="em_santa", speed=1.0, output_format="ogg")
            if res.get("file_path") and os.path.exists(res["file_path"]):
                return Path(res["file_path"])
        except Exception as e:
            print(f"[CreativeVoiceEngine Error, fallback to Piper/espeak]: {e}")

        # 2. Fallback: Piper TTS si está configurado
        try:
            from piper import PiperVoice
            import wave
            import io

            model_path = Path.home() / "ai-lab/scripts/voice/tts_models/es_MX-ald-medium.onnx"
            config_path = Path.home() / "ai-lab/scripts/voice/tts_models/es_MX-ald-medium.onnx.json"

            if model_path.exists() and config_path.exists():
                voice = PiperVoice.load(str(model_path), config_path=str(config_path), use_cuda=False)
                with wave.open(str(temp_wav), "wb") as wav_file:
                    voice.synthesize(clean_text, wav_file)

                # Convertir a OGG Opus para Telegram
                cmd = [
                    "ffmpeg", "-y",
                    "-i", str(temp_wav),
                    "-c:a", "libopus",
                    "-b:a", "32k",
                    str(out_ogg)
                ]
                subprocess.run(cmd, capture_output=True, check=True)
                if out_ogg.exists() and out_ogg.stat().st_size > 0:
                    return out_ogg
        except Exception as e:
            print(f"[TTS Piper Error]: {e}")

        # 2. Fallback: spd-say / espeak-ng / ffmpeg
        if shutil_which := subprocess.run(["which", "espeak-ng"], capture_output=True).stdout.decode().strip():
            try:
                cmd_espeak = [
                    shutil_which,
                    "-v", "es-la",
                    "-s", "160",
                    "-w", str(temp_wav),
                    clean_text
                ]
                subprocess.run(cmd_espeak, capture_output=True, check=True)
                cmd_ffmpeg = [
                    "ffmpeg", "-y",
                    "-i", str(temp_wav),
                    "-c:a", "libopus",
                    "-b:a", "32k",
                    str(out_ogg)
                ]
                subprocess.run(cmd_ffmpeg, capture_output=True, check=True)
                if out_ogg.exists() and out_ogg.stat().st_size > 0:
                    return out_ogg
            except Exception as e:
                print(f"[TTS espeak fallback error]: {e}")

        return None
