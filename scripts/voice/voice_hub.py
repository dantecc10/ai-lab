import argparse
import asyncio
import signal
import sys
import os
import numpy as np
import pyaudio
import sounddevice as sd
from faster_whisper import WhisperModel
from openwakeword.model import Model
from assistant import run_conversation

# ── Configuración ─────────────────────────────────────────
import openwakeword
WAKE_MODELS_DIR = os.path.join(os.path.dirname(openwakeword.__file__), "resources", "models")
WAKE_MODELS = [
    os.path.join(WAKE_MODELS_DIR, "hey_jarvis_v0.1.onnx"),
    os.path.join(WAKE_MODELS_DIR, "alexa_v0.1.onnx")
]
WAKE_THRESHOLD = 0.55
WHISPER_MODEL = "base"
SAMPLE_RATE = 16000
FRAMES_PER_BUFFER = 1280

# ── Logging ───────────────────────────────────────────────
def log(msg, level="info"):
    icons = {"info": "[i]", "ok": "[+]", "warn": "[!]", "error": "[x]"}
    print(f"{icons.get(level, '[i]')} {msg}", flush=True)

# ── Inicialización (lazy) ─────────────────────────────────
_whisper_engine = None
_wake_model = None

def get_whisper():
    global _whisper_engine
    if _whisper_engine is None:
        log("Cargando Whisper (CPU, int8)...")
        _whisper_engine = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        log("Whisper listo", "ok")
    return _whisper_engine

def get_wake_model():
    global _wake_model
    if _wake_model is None:
        model_names = [os.path.basename(m).replace("_v0.1.onnx", "") for m in WAKE_MODELS]
        log(f"Cargando modelos wake word: {', '.join(model_names)}...")
        _wake_model = Model(wakeword_model_paths=WAKE_MODELS)
        log("Wake word listo", "ok")
    return _wake_model

# ── Audio ─────────────────────────────────────────────────
def record_audio(duration: float = 4.0) -> np.ndarray:
    log(f"Grabando {duration}s de audio...")
    recording = sd.rec(int(duration * SAMPLE_RATE), samplerate=SAMPLE_RATE, channels=1, dtype='float32')
    sd.wait()
    return recording.flatten()

def transcribe(audio_data: np.ndarray) -> str:
    log("Transcribiendo con Whisper...")
    whisper = get_whisper()
    segments, _ = whisper.transcribe(audio_data, language="es")
    return " ".join([segment.text for segment in segments]).strip()

# ── Flujo de voz ──────────────────────────────────────────
def handle_voice_flow(duration: float = 4.0):
    audio = record_audio(duration=duration)
    text = transcribe(audio)
    if text:
        log(f"Transcripción: \"{text}\"", "ok")
        asyncio.run(run_conversation(text))
    else:
        log("No se capturó audio comprensible", "warn")

# ── Push-to-Talk (para atajo de teclado) ──────────────────
def run_push_to_talk(duration: float):
    log("Modo Push-to-Talk activado")
    handle_voice_flow(duration=duration)

# ── Wake Word Listener (daemon) ───────────────────────────
def run_wake_listener(threshold: float):
    log("Modo Wake Word activo en segundo plano")
    model_names = [os.path.basename(m).replace("_v0.1.onnx", "") for m in WAKE_MODELS]
    log(f"Palabras activas: {', '.join(model_names)}")
    log("Esperando llamada...")

    wake_model = get_wake_model()
    pa = pyaudio.PyAudio()
    mic_stream = pa.open(
        format=pyaudio.paInt16,
        channels=1,
        rate=SAMPLE_RATE,
        input=True,
        frames_per_buffer=FRAMES_PER_BUFFER
    )

    # Graceful shutdown
    running = True
    def handle_signal(sig, frame):
        nonlocal running
        running = False
        log("Señal recibida, deteniendo...")
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    try:
        while running:
            audio_frame = np.frombuffer(
                mic_stream.read(FRAMES_PER_BUFFER, exception_on_overflow=False),
                dtype=np.int16
            )
            predictions = wake_model.predict(audio_frame)

            triggered_word = None
            for model_name in WAKE_MODELS:
                if predictions.get(model_name, 0) >= threshold:
                    triggered_word = model_name
                    break

            if triggered_word:
                log(f"Activación por '{triggered_word}'", "ok")
                mic_stream.stop_stream()

                handle_voice_flow(duration=4.5)

                wake_model.reset()
                mic_stream.start_stream()
                log("Esperando siguiente comando...")
    finally:
        mic_stream.stop_stream()
        mic_stream.close()
        pa.terminate()
        log(" Listener detenido")

# ── Main ──────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Hub de control por voz para domótica Kasa + LLM local"
    )
    parser.add_argument(
        "--mode",
        choices=["ptt", "listen", "daemon"],
        default="listen",
        help="ptt=Push-to-Talk | listen=Wake Word | daemon=Wake Word (systemd)"
    )
    parser.add_argument(
        "--duration", type=float, default=4.0,
        help="Duración de grabación en segundos (default: 4.0)"
    )
    parser.add_argument(
        "--threshold", type=float, default=WAKE_THRESHOLD,
        help="Sensibilidad wake word 0.0-1.0 (default: 0.55)"
    )

    args = parser.parse_args()

    if args.mode == "ptt":
        run_push_to_talk(duration=args.duration)
    elif args.mode == "daemon":
        # Daemon mode: log to stdout for journalctl
        run_wake_listener(threshold=args.threshold)
    else:
        run_wake_listener(threshold=args.threshold)
