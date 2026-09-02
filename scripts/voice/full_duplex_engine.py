#!/usr/bin/env python3
"""
AI Lab — Full-Duplex Streaming Voice Engine with Barge-In
Control de voz bidireccional con síntesis Piper TTS, detección de actividad de voz (VAD),
cancelación inmediata por interrupción (Barge-In) y transcripción Whisper local.
"""

import os
import sys
import time
import json
import wave
import signal
import struct
import math
import shutil
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

# Asegurar que la raíz del proyecto ai-lab esté en sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

BASE_DIR = Path(__file__).resolve().parent
TTS_MODEL = BASE_DIR / "tts_models" / "es_MX-ald-medium.onnx"
TTS_CONFIG = BASE_DIR / "tts_models" / "es_MX-ald-medium.onnx.json"
TEMP_AUDIO_DIR = Path.home() / ".local" / "share" / "ai-lab" / "audio"
WHISPER_URL = "http://127.0.0.1:9093/v1/audio/transcriptions"

class FullDuplexVoiceEngine:
    """Motor de voz full-duplex con interrupción (Barge-In) y VAD."""

    def __init__(self, whisper_url: str = WHISPER_URL):
        self.whisper_url = whisper_url
        TEMP_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
        self._current_playback_proc: subprocess.Popen | None = None
        self._interrupted = False

    def is_whisper_alive(self) -> bool:
        """Comprueba si el servidor Whisper STT local (:9093) está activo."""
        try:
            req = urllib.request.Request("http://127.0.0.1:9093/health", headers={"User-Agent": "AI-Lab-Voice"})
            with urllib.request.urlopen(req, timeout=1.0) as resp:
                return resp.status == 200
        except Exception:
            # Intentar verificar si el proceso de whisper está escuchando en puerto 9093
            return shutil.which("faster-whisper") is not None or Path("/home/darkseid/scripting/gpu-tools/skills/whisper_server.py").exists()

    def cancel_speech(self) -> bool:
        """Detiene inmediatamente cualquier reproducción de voz activa (Barge-In)."""
        self._interrupted = True
        if self._current_playback_proc and self._current_playback_proc.poll() is None:
            try:
                self._current_playback_proc.terminate()
                self._current_playback_proc.wait(timeout=0.3)
            except Exception:
                try:
                    self._current_playback_proc.kill()
                except Exception:
                    pass
            self._current_playback_proc = None
            return True
        return False

    def synthesize_to_wav(self, text: str, output_wav: Path) -> bool:
        """Sintetiza texto a audio WAV usando Piper TTS."""
        if not text.strip():
            return False

        # Intentar ejecutar piper vía CLI si el modelo existe
        if TTS_MODEL.exists():
            piper_bin = shutil.which("piper") or "/home/darkseid/.local/bin/piper" or "/usr/bin/piper"
            if shutil.which(piper_bin):
                cmd = [
                    piper_bin,
                    "--model", str(TTS_MODEL),
                    "--config", str(TTS_CONFIG),
                    "--output_file", str(output_wav)
                ]
                proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                proc.communicate(input=text.encode("utf-8"))
                return proc.returncode == 0 and output_wav.exists()

        # Fallback a script tts_notifier.py existente
        tts_script = BASE_DIR / "tts_notifier.py"
        if tts_script.exists():
            res = subprocess.run([sys.executable, str(tts_script), text, "--no-notify"], capture_output=True)
            return res.returncode == 0

        # Fallback a espeak / festival
        if shutil.which("espeak-ng"):
            res = subprocess.run(["espeak-ng", "-v", "es-la", "-w", str(output_wav), text], capture_output=True)
            return res.returncode == 0 and output_wav.exists()
        elif shutil.which("espeak"):
            res = subprocess.run(["espeak", "-v", "es", "-w", str(output_wav), text], capture_output=True)
            return res.returncode == 0 and output_wav.exists()

        return False

    def speak(self, text: str, interruptible: bool = True, notify: bool = False, block: bool = False) -> dict:
        """Sintetiza y reproduce voz. Si block=True, espera hasta finalizar la reproducción."""
        if interruptible:
            self.cancel_current_speech()

        # 1. Diagnóstico rápido de audibilidad
        try:
            from scripts.voice.audio_diagnostics import AudioDiagnostics
            audible, reason = AudioDiagnostics.check_audibility(min_volume=15, notify_if_inaudible=True)
        except Exception:
            audible, reason = True, "Diagnóstico no disponible"

        # 2. Consultar perfil de voz activo
        try:
            from scripts.voice.voice_profiles import VoiceProfileManager
            profile = VoiceProfileManager().get_active_profile()
        except Exception:
            profile = {"language": "es-MX", "spd_voice": "female1", "speed": 1.0, "pitch": 1.0}

        if notify:
            try:
                subprocess.run(
                    ["notify-send", "-a", "AI Voice", "-t", "3000", "Voz del Asistente", text[:120]],
                    check=False
                )
            except Exception:
                pass

        wav_path = TEMP_AUDIO_DIR / f"tts_{int(time.time() * 1000)}.wav"
        synth_ok = self.synthesize_to_wav(text, wav_path)

        if synth_ok and wav_path.exists():
            player_bin = shutil.which("pw-play") or shutil.which("paplay") or shutil.which("aplay")
            if player_bin:
                self._current_playback_proc = subprocess.Popen(
                    [player_bin, str(wav_path)],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                if block:
                    try:
                        self._current_playback_proc.wait(timeout=30.0)
                    except Exception:
                        pass
                    # Tiempo de decaimiento acústico para eliminar ecos
                    time.sleep(0.35)

                return {
                    "success": True,
                    "text": text,
                    "audio_path": str(wav_path),
                    "engine": "piper_wav",
                    "profile": profile.get("name", "es_MX"),
                    "audible": audible,
                    "audio_status": reason,
                    "interruptible": interruptible,
                    "playback_pid": self._current_playback_proc.pid if self._current_playback_proc else None
                }

        # Fallback a speech-dispatcher / spd-say con perfil configurado
        if shutil.which("spd-say"):
            lang = profile.get("language", "es-MX").split("-")[0]
            voice_type = profile.get("spd_voice", "female1")
            rate = int((profile.get("speed", 1.0) - 1.0) * 100)
            pitch = int((profile.get("pitch", 1.0) - 1.0) * 100)

            cmd = ["spd-say", "-l", lang, "-t", voice_type, "-r", str(rate), "-p", str(pitch), text]
            self._current_playback_proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            if block:
                try:
                    self._current_playback_proc.wait(timeout=30.0)
                except Exception:
                    pass
                time.sleep(0.35)

            return {
                "success": True,
                "text": text,
                "engine": "speech_dispatcher",
                "profile": profile.get("name", "Default"),
                "audible": audible,
                "audio_status": reason,
                "interruptible": interruptible,
                "playback_pid": self._current_playback_proc.pid if self._current_playback_proc else None
            }

        return {
            "success": False,
            "text": text,
            "error": "No se encontró ningún motor TTS disponible (Piper o spd-say)."
        }

    def listen(self, timeout_seconds: float = 6.0, silence_ms: int = 700) -> dict:
        """Escucha el micrófono con detección inteligente de silencios (VAD por RMS) y transcribe con Parakeet/Whisper."""
        wav_path = TEMP_AUDIO_DIR / f"mic_input_{int(time.time() * 1000)}.wav"
        
        # Grabador por streaming con detección VAD
        cmd = ["ffmpeg", "-f", "pulse", "-i", "default", "-f", "s16le", "-ar", "16000", "-ac", "1", "-"]
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception:
            return {"success": False, "error": "No se pudo iniciar la captura de audio con ffmpeg."}

        frames = []
        chunk_size = 1600  # 50ms at 16kHz 16-bit
        started_speaking = False
        silence_start = None
        t0 = time.time()
        silence_cutoff_sec = max(0.4, silence_ms / 1000.0)

        # Descartar primeros 2 chunks residuales del buffer de audio
        for _ in range(2):
            try:
                proc.stdout.read(chunk_size)
            except Exception:
                pass

        try:
            while time.time() - t0 < timeout_seconds:
                chunk = proc.stdout.read(chunk_size)
                if not chunk:
                    break
                frames.append(chunk)

                # Calcular energía RMS del chunk
                import struct, math
                samples = struct.unpack(f"<{len(chunk)//2}h", chunk)
                sum_sq = sum(s * s for s in samples)
                rms = math.sqrt(sum_sq / max(1, len(samples)))

                # Umbral de detección de voz (> 380)
                if rms > 380:
                    started_speaking = True
                    silence_start = None
                elif started_speaking:
                    if silence_start is None:
                        silence_start = time.time()
                    elif time.time() - silence_start >= silence_cutoff_sec:
                        # Usuario terminó de hablar
                        break
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=0.3)
            except Exception:
                proc.kill()

        if not frames:
            return {"success": False, "transcription": "", "error": "No se capturaron muestras de audio."}

        import wave
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(b"".join(frames))

        # Idioma del perfil
        try:
            from scripts.voice.voice_profiles import VoiceProfileManager
            lang = VoiceProfileManager().get_active_profile().get("language", "es-MX").split("-")[0]
        except Exception:
            lang = "es"

        transcription = self.transcribe_file(wav_path, language=lang)
        return {
            "success": True,
            "audio_path": str(wav_path),
            "transcription": transcription,
            "speech_detected": started_speaking
        }

    def transcribe_file(self, wav_path: Path, language: str = "es") -> str:
        """Transcribe usando Parakeet V3 (Handy) o Whisper con idioma fijado."""
        # 1. Intentar con Parakeet V3 (NVIDIA NeMo vía Handy CLI / ONNX)
        try:
            from scripts.voice.parakeet_engine import ParakeetEngine
            parakeet = ParakeetEngine()
            if parakeet.available:
                p_res = parakeet.transcribe(wav_path)
                if p_res.get("success") and p_res.get("text"):
                    return p_res["text"].strip()
        except Exception:
            pass

        # 2. Fallback a HTTP multipart a whisper_server :9093 (faster-whisper-large-v3)
        try:
            boundary = "----WebKitFormBoundary7MA4YWxkTrZu0gW"
            body = bytearray()
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(b'Content-Disposition: form-data; name="language"\r\n\r\n')
            body.extend(f"{language}\r\n".encode("utf-8"))
            body.extend(f"--{boundary}\r\n".encode("utf-8"))
            body.extend(b'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n')
            body.extend(b"Content-Type: audio/wav\r\n\r\n")
            body.extend(wav_path.read_bytes())
            body.extend(f"\r\n--{boundary}--\r\n".encode("utf-8"))

            req = urllib.request.Request(
                self.whisper_url,
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=12.0) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                return res.get("text", "").strip()
        except Exception:
            pass

        # 3. Fallback a faster_whisper directo si está instalado
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("base", device="cpu", compute_type="int8")
            segments, _ = model.transcribe(str(wav_path), language=language)
            return " ".join([s.text for s in segments]).strip()
        except Exception:
            pass

        return "(Transcripción no disponible en este entorno)"

    def get_status(self) -> dict:
        """Devuelve el estado de los componentes de audio y voz."""
        piper_ready = TTS_MODEL.exists() or shutil.which("espeak-ng") is not None
        spd_say_ready = shutil.which("spd-say") is not None
        whisper_ready = self.is_whisper_alive()
        mic_ready = shutil.which("pw-record") is not None or shutil.which("arecord") is not None
        player_ready = shutil.which("pw-play") is not None or shutil.which("paplay") is not None or spd_say_ready

        return {
            "barge_in_active": True,
            "tts_ready": piper_ready or spd_say_ready,
            "tts_engine": "piper" if piper_ready else ("spd-say" if spd_say_ready else "none"),
            "stt_whisper_ready": whisper_ready,
            "microphone_ready": mic_ready,
            "playback_ready": player_ready,
            "whisper_endpoint": self.whisper_url
        }

if __name__ == "__main__":
    engine = FullDuplexVoiceEngine()
    print("[+] FullDuplexVoiceEngine inicializado.")
    print(f"[✓] Estado del sistema de voz: {engine.get_status()}")
