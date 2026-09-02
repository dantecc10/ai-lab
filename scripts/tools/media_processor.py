#!/usr/bin/env python3
"""
AI Lab — Media, YouTube & Audio/Video Processor
Motor de descarga, transcripción y resumen multimedia con Whisper y yt-dlp:
  - Descarga de audio y video desde YouTube, X, TikTok, Reddit, Podcasts, etc.
  - Transcripción de audio a texto mediante Whisper STT local (:9093)
  - Resumen inteligente estructurado con Gemma 4 (LLM local :9090)
  - Generación de subtítulos (.srt, .vtt, .txt)
"""

import os
import sys
import json
import shutil
import urllib.request
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any, List

MEDIA_DIR = Path(os.path.expanduser("~/.local/share/ai-lab/media"))
MEDIA_DIR.mkdir(parents=True, exist_ok=True)

WHISPER_URL = os.environ.get("WHISPER_URL", "http://127.0.0.1:9093/v1/audio/transcriptions")
LLM_URL = os.environ.get("LLM_URL", "http://127.0.0.1:9090/v1/chat/completions")


class MediaProcessor:
    """Procesador multimedia para YouTube, audio, video y transcripciones."""

    def __init__(self, media_dir: Path = MEDIA_DIR, whisper_url: str = WHISPER_URL, llm_url: str = LLM_URL):
        self.media_dir = media_dir
        self.whisper_url = whisper_url
        self.llm_url = llm_url

    def download_media(
        self,
        url: str,
        media_type: str = "audio",  # 'audio' o 'video'
        quality: str = "best"
    ) -> Dict[str, Any]:
        """Descarga audio o video de cualquier plataforma compatible con yt-dlp."""
        import yt_dlp

        out_template = str(self.media_dir / "%(title).60s_%(id)s.%(ext)s")
        
        ydl_opts = {
            "outtmpl": out_template,
            "quiet": True,
            "no_warnings": True,
        }

        if media_type == "audio":
            ydl_opts.update({
                "format": "bestaudio/best",
                "postprocessors": [{
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }],
            })
        else:
            ydl_opts.update({
                "format": "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
                "merge_output_format": "mp4",
            })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            if media_type == "audio":
                filename = str(Path(filename).with_suffix(".mp3"))

            return {
                "title": info.get("title", "Desconocido"),
                "duration": info.get("duration", 0),
                "uploader": info.get("uploader", "N/A"),
                "file_path": filename,
                "file_size_mb": round(os.path.getsize(filename) / (1024 * 1024), 2) if os.path.exists(filename) else 0,
                "media_type": media_type,
                "webpage_url": info.get("webpage_url", url)
            }

    def convert_to_wav_16k(self, input_path: str) -> str:
        """Convierte cualquier archivo de audio/video a WAV 16kHz mono optimizado para Whisper."""
        out_wav = str(Path(input_path).with_suffix(".16k.wav"))
        if os.path.exists(out_wav):
            return out_wav

        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-ar", "16000", "-ac", "1", "-c:a", "pcm_s16le",
            out_wav
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if res.returncode != 0:
            raise RuntimeError(f"Error convirtiendo audio con ffmpeg: {res.stderr}")
        return out_wav

    def transcribe_audio_file(self, file_path: str, language: Optional[str] = None) -> str:
        """Transcribe un archivo local enviándolo al servidor Whisper STT (:9093)."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        # Optimizar audio a 16kHz mono
        wav_path = self.convert_to_wav_16k(file_path)

        import requests
        with open(wav_path, "rb") as f:
            files = {"file": (os.path.basename(wav_path), f, "audio/wav")}
            data = {"model": "whisper-base"}
            if language:
                data["language"] = language

            response = requests.post(self.whisper_url, files=files, data=data, timeout=180)

        if response.status_code == 200:
            res_json = response.json()
            return res_json.get("text", "").strip()
        else:
            raise RuntimeError(f"Error en servidor Whisper (HTTP {response.status_code}): {response.text}")

    def process_and_transcribe(self, url_or_path: str, language: Optional[str] = None) -> Dict[str, Any]:
        """Descarga (si es URL) y transcribe el audio completo."""
        if url_or_path.startswith("http://") or url_or_path.startswith("https://"):
            dl_info = self.download_media(url_or_path, media_type="audio")
            audio_path = dl_info["file_path"]
            title = dl_info["title"]
            duration = dl_info["duration"]
            uploader = dl_info["uploader"]
        else:
            audio_path = url_or_path
            title = Path(url_or_path).name
            duration = 0
            uploader = "Local"

        transcription = self.transcribe_audio_file(audio_path, language=language)

        # Guardar transcripción en archivo de texto
        txt_path = str(Path(audio_path).with_suffix(".txt"))
        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(transcription)

        return {
            "title": title,
            "uploader": uploader,
            "duration_sec": duration,
            "audio_path": audio_path,
            "transcript_path": txt_path,
            "text": transcription,
            "word_count": len(transcription.split())
        }

    def summarize_video_or_audio(self, url_or_path: str) -> Dict[str, Any]:
        """Descarga, transcribe y genera un resumen estructurado con Gemma 4."""
        trans_res = self.process_and_transcribe(url_or_path)
        text = trans_res["text"]

        if not text:
            return {
                **trans_res,
                "summary": "No se pudo extraer texto suficiente para generar un resumen."
            }

        # Enviar transcripción a Gemma 4 para resumir
        prompt = f"""Eres un analista de contenido y asistente de IA de alto nivel.
A continuación tienes la transcripción completa del contenido titulado "{trans_res['title']}":

\"\"\"{text[:16000]}\"\"\"

Por favor, genera un RESUMEN ESTRUCTURADO Y DE ALTO VALOR con el siguiente formato Markdown:

# 🎬 {trans_res['title']}
**Canal/Autor:** {trans_res['uploader']}

### 🎯 Tesis / Idea Principal:
(1-2 oraciones claras que sinteticen el mensaje central)

### 📌 Puntos Clave & Argumentos:
• **Punto 1:** Explicación
• **Punto 2:** Explicación
• **Punto 3:** Explicación

### 💡 Conclusiones & Aprendizajes Destacados:
(Ideas prácticas o conclusiones finales)
"""

        import requests
        payload = {
            "model": "gemma-4-12b-it",
            "messages": [
                {"role": "system", "content": "Eres un asistente experto en síntesis y análisis de contenido multimedia."},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.4,
            "max_tokens": 2048
        }

        try:
            res = requests.post(self.llm_url, json=payload, timeout=90)
            if res.status_code == 200:
                summary_text = res.json()["choices"][0]["message"]["content"]
            else:
                summary_text = f"Error en LLM (HTTP {res.status_code}): {res.text}"
        except Exception as e:
            summary_text = f"Error generando resumen con Gemma 4: {e}"

        # Guardar resumen en archivo markdown
        summary_path = str(Path(trans_res["audio_path"]).with_name(f"{Path(trans_res['audio_path']).stem}_resumen.md"))
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(summary_text)

        return {
            **trans_res,
            "summary": summary_text,
            "summary_path": summary_path
        }


# Singleton
media_processor = MediaProcessor()


if __name__ == "__main__":
    if len(sys.argv) > 1:
        test_url = sys.argv[1]
        print(f"Procesando: {test_url}")
        res = media_processor.summarize_video_or_audio(test_url)
        print("\n" + res["summary"])
