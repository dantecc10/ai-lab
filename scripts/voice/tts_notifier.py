import sys
import os
import subprocess
import wave
import io
import sounddevice as sd
from piper import PiperVoice

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(BASE_DIR, "tts_models/es_MX-ald-medium.onnx")
CONFIG_PATH = os.path.join(BASE_DIR, "tts_models/es_MX-ald-medium.onnx.json")

def send_notification(title: str, text: str):
    """Envía notificación nativa a Pop!_OS vía notify-send."""
    try:
        subprocess.run(
            ["notify-send", "-a", "Asistente Kasa", "-t", "3500", title, text],
            check=False
        )
    except Exception:
        pass

def speak(text: str, notify: bool = True, notify_title: str = "Gemma"):
    """Sintetiza voz en CPU con Piper y reproduce directamente por PipeWire/PulseAudio."""
    if notify:
        send_notification(notify_title, text)
    
    if not text.strip():
        return

    try:
        # Cargar modelo en CPU
        voice = PiperVoice.load(MODEL_PATH, config_path=CONFIG_PATH, use_cuda=False)
        
        # Buffer de audio en memoria
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wav_file:
            voice.synthesize(text, wav_file)
        
        wav_io.seek(0)
        with wave.open(wav_io, "rb") as wf:
            samplerate = wf.getframerate()
            audio_data = wf.readframes(wf.getnframes())
            # Convertir PCM 16-bit a array numpy para sounddevice
            import numpy as np
            audio_np = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(audio_np, samplerate=samplerate)
            sd.wait()
    except Exception as e:
        print(f"[Error TTS]: {e}", file=sys.stderr)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python3 tts_notifier.py \"Texto a hablar\" [--no-notify]")
        sys.exit(1)

    message = sys.argv[1]
    with_notify = "--no-notify" not in sys.argv
    speak(message, notify=with_notify)
