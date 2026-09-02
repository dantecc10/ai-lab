#!/usr/bin/env python3
"""
Whisper API Server — Speech-to-Text for Open WebUI and llama.cpp
Provides OpenAI-compatible /v1/audio/transcriptions endpoint.
"""

import os
import sys
import json
import tempfile
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

import os
import sys
import json
import tempfile
import subprocess
import configparser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

# Add venv site-packages
skills_venv = os.path.expanduser("~/scripting/gpu-tools/skills/.venv/lib/python3.12/site-packages")
if os.path.exists(skills_venv) and skills_venv not in sys.path:
    sys.path.insert(0, skills_venv)

HOST = "0.0.0.0"
PORT = 9093

# Global model instance
whisper_model = None

DEFAULT_WHISPER_CONF = Path.home() / ".config" / "ai-lab" / "whisper.conf"
REPO_WHISPER_CONF = Path(__file__).resolve().parent.parent.parent / "configs" / "whisper.conf"


def get_whisper_config() -> dict:
    conf = configparser.ConfigParser()
    if DEFAULT_WHISPER_CONF.exists():
        conf.read(DEFAULT_WHISPER_CONF)
    elif REPO_WHISPER_CONF.exists():
        conf.read(REPO_WHISPER_CONF)

    return {
        "model": conf.get("whisper", "model", fallback="small"),
        "device": conf.get("whisper", "device", fallback="cpu"),
        "compute_type": conf.get("whisper", "compute_type", fallback="int8"),
        "cpu_threads": conf.getint("whisper", "cpu_threads", fallback=8),
        "language": conf.get("whisper", "language", fallback="es"),
        "beam_size": conf.getint("whisper", "beam_size", fallback=3),
        "vad_filter": conf.getboolean("whisper", "vad_filter", fallback=True)
    }


def load_model():
    global whisper_model
    if whisper_model is None:
        from faster_whisper import WhisperModel
        cfg = get_whisper_config()
        model_name = cfg["model"]
        print(f"Loading Whisper model ({model_name}, {cfg['device']} {cfg['compute_type']})...")
        whisper_model = WhisperModel(
            model_name,
            device=cfg["device"],
            compute_type=cfg["compute_type"],
            cpu_threads=cfg["cpu_threads"]
        )
        print(f"Whisper model ({model_name}) loaded successfully!")
    return whisper_model


class WhisperHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.end_headers()

    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)

        if parsed.path == "/v1/models":
            self.send_json({
                "object": "list",
                "data": [{
                    "id": "whisper-base",
                    "object": "model",
                    "owned_by": "local"
                }]
            })
        elif parsed.path == "/health":
            self.send_json({"status": "ok"})
        else:
            self.send_error(404)

    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)

        if parsed.path == "/v1/audio/transcriptions":
            self.handle_transcription()
        else:
            self.send_error(404)

    def handle_transcription(self):
        """Handle audio transcription"""
        try:
            content_type = self.headers.get("Content-Type", "")

            if "multipart/form-data" in content_type:
                # Parse multipart form data
                boundary = content_type.split("boundary=")[1].encode()
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)

                # Simple multipart parser
                parts = body.split(b"--" + boundary)
                audio_data = None
                filename = "audio.wav"
                language = None

                for part in parts:
                    if b"Content-Disposition" in part:
                        if b'name="file"' in part:
                            # Extract audio data
                            header_end = part.find(b"\r\n\r\n")
                            if header_end != -1:
                                audio_data = part[header_end + 4:]
                                if audio_data.endswith(b"\r\n"):
                                    audio_data = audio_data[:-2]

                            # Try to get filename
                            if b'filename="' in part:
                                start = part.find(b'filename="') + 10
                                end = part.find(b'"', start)
                                if end != -1:
                                    filename = part[start:end].decode()
                        elif b'name="model"' in part:
                            header_end = part.find(b"\r\n\r\n")
                            if header_end != -1:
                                pass  # We ignore model name, use our local model
                        elif b'name="language"' in part:
                            header_end = part.find(b"\r\n\r\n")
                            if header_end != -1:
                                language = part[header_end + 4:].decode().strip()

                if audio_data is None:
                    self.send_json({"error": "No audio data provided"}, 400)
                    return

                # Save audio to temp file
                suffix = os.path.splitext(filename)[1] or ".wav"
                with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                    tmp.write(audio_data)
                    tmp_path = tmp.name

                wav_16k_path = tmp_path + "_16k.wav"
                try:
                    # Convert to 16kHz mono WAV for optimal ASR performance
                    subprocess.run(
                        ["ffmpeg", "-y", "-i", tmp_path, "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le", wav_16k_path],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        check=False
                    )
                    audio_target = wav_16k_path if os.path.exists(wav_16k_path) and os.path.getsize(wav_16k_path) > 0 else tmp_path

                    # 1. Intentar con Parakeet V3 (NVIDIA NeMo)
                    try:
                        from scripts.voice.parakeet_engine import ParakeetEngine
                        parakeet = ParakeetEngine()
                        if parakeet.available:
                            p_res = parakeet.transcribe(audio_target)
                            if p_res.get("success") and p_res.get("text"):
                                self.send_json({
                                    "text": p_res["text"].strip(),
                                    "language": "es",
                                    "duration": p_res.get("duration_sec", 0.0),
                                    "latency_ms": p_res.get("latency_ms", 0),
                                    "engine": "parakeet_tdt_v3"
                                })
                                return
                    except Exception as pe:
                        print(f"[Parakeet Attempt Error, falling back to Whisper]: {pe}")

                    # 2. Fallback a faster-whisper
                    model = load_model()
                    cfg = get_whisper_config()
                    target_lang = language or cfg.get("language", "es")
                    segments, info = model.transcribe(
                        audio_target,
                        language=target_lang,
                        beam_size=cfg.get("beam_size", 3),
                        vad_filter=cfg.get("vad_filter", True)
                    )

                    text = " ".join([seg.text for seg in segments])

                    self.send_json({
                        "text": text.strip(),
                        "language": info.language,
                        "duration": info.duration,
                        "engine": "faster_whisper"
                    })
                finally:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                    if os.path.exists(wav_16k_path):
                        os.unlink(wav_16k_path)

            else:
                self.send_json({"error": "Expected multipart/form-data"}, 400)

        except Exception as e:
            print(f"Error: {e}")
            self.send_json({"error": str(e)}, 500)

    def send_json(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def log_message(self, format, *args):
        """Log requests"""
        print(f"[{self.log_date_time_string()}] {format % args}")


def main():
    # Pre-load model
    load_model()

    server = HTTPServer((HOST, PORT), WhisperHandler)
    print(f"Whisper API Server running on http://{HOST}:{PORT}")
    print(f"Endpoint: http://localhost:{PORT}/v1/audio/transcriptions")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
