"""Voice synthesis/listening, vision/OCR, audio devices, desktop context, and Handy integration."""

import os
import subprocess


from mcp_common.logging import log_operation

TOOLS = [
    # ── Voice Tools ────────────────────────────────────────
    {
        "name": "voice_speak",
        "description": "Sintetiza y reproduce voz en tiempo real con soporte de interrupcion bidireccional (Barge-In).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Texto a hablar."
                },
                "interruptible": {
                    "type": "boolean",
                    "description": "Permite interrumpir la reproduccion si se detecta voz del usuario (default: true)."
                },
                "notify": {
                    "type": "boolean",
                    "description": "Enviar notificacion visual de escritorio en Pop!_OS (default: true)."
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "voice_listen",
        "description": "Escucha el microfono con Voice Activity Detection (VAD) inteligente y transcribe el audio a texto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "timeout_seconds": {
                    "type": "number",
                    "description": "Tiempo maximo de escucha en segundos (default: 8.0)."
                },
                "silence_ms": {
                    "type": "integer",
                    "description": "Milisegundos de silencio para cortar la grabacion automaticamente (default: 800)."
                }
            }
        }
    },
    {
        "name": "voice_status",
        "description": "Consulta el estado de los componentes de voz (Piper TTS, Whisper STT, microfono y Barge-In).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "voice_set_profile",
        "description": "Personaliza el perfil de voz, idioma, acento, velocidad y tono del asistente (ej: 'es_MX_alvaro', 'es_ES_castilian', 'en_US_natural', 'en_GB_british', 'fast_assistant').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "profile_id": {
                    "type": "string",
                    "description": "Identificador del perfil de voz."
                },
                "language": {
                    "type": "string",
                    "description": "Codigo de idioma (ej: 'es-MX', 'es-ES', 'en-US', 'en-GB')."
                },
                "speed": {
                    "type": "number",
                    "description": "Velocidad de habla (0.5 a 2.5, default: 1.0)."
                },
                "pitch": {
                    "type": "number",
                    "description": "Tono de voz (0.5 a 2.0, default: 1.0)."
                },
                "volume": {
                    "type": "integer",
                    "description": "Volumen de voz del sintetizador (10 a 150)."
                }
            },
            "required": ["profile_id"]
        }
    },
    {
        "name": "voice_list_profiles",
        "description": "Lista todos los perfiles de voz, acentos e idiomas disponibles para el asistente.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "voice_conversational_turn",
        "description": "Ejecuta un ciclo conversacional completo por voz (escucha microfono con VAD, procesa con LLM y responde por voz con Barge-In).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Prompt inicial opcional para arrancar la conversacion."
                }
            }
        }
    },
    {
        "name": "voice_transcribe_audio",
        "description": "Transcribe un archivo de audio WAV usando Parakeet V3 (Handy) o Whisper con la maxima precision.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Ruta al archivo WAV a transcribir."
                },
                "engine": {
                    "type": "string",
                    "description": "Motor ASR preferido ('parakeet', 'whisper' o 'auto'). Default: 'auto'."
                }
            },
            "required": ["file_path"]
        }
    },
    # ── Vision Tools ───────────────────────────────────────
    {
        "name": "vision_analyze_image",
        "description": "Realiza inferencia visual multimodal u OCR sobre una imagen local o captura de pantalla.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Ruta absoluta o relativa del archivo de imagen."
                },
                "prompt": {
                    "type": "string",
                    "description": "Pregunta o instruccion de analisis visual (default: 'Describe esta imagen en detalle')."
                }
            },
            "required": ["image_path"]
        }
    },
    {
        "name": "vision_inspect_screen",
        "description": "Captura la pantalla del escritorio en tiempo real y ejecuta analisis visual multimodal sobre el contenido.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "Pregunta o instruccion para el analisis de la pantalla (default: 'Describe la actividad actual en pantalla')."
                }
            }
        }
    },
    {
        "name": "vision_ocr",
        "description": "Extrae el texto completo de una imagen mediante el motor local Tesseract OCR.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Ruta de la imagen a procesar."
                }
            },
            "required": ["image_path"]
        }
    },
    # ── Audio Tools ────────────────────────────────────────
    {
        "name": "audio_list_devices",
        "description": "Lista dispositivos de audio del sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "audio_set_source",
        "description": "Cambia la fuente de audio (sink).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sink": {
                    "type": "string",
                    "description": "Nombre del sink (dispositivo de salida)."
                }
            },
            "required": ["sink"]
        }
    },
    {
        "name": "audio_set_source_input",
        "description": "Cambia la fuente de entrada de audio (source).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Nombre del source (dispositivo de entrada)."
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "audio_check_volume",
        "description": "Diagnostica el volumen del sistema y el estado de mute, alertando con notificacion de escritorio si el audio no es audible para conversar.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "min_volume": {
                    "type": "integer",
                    "description": "Porcentaje minimo de volumen requerido (default: 15)."
                },
                "notify_if_inaudible": {
                    "type": "boolean",
                    "description": "Enviar notificacion si las bocinas estan silenciadas o muy bajas (default: true)."
                }
            }
        }
    },
    {
        "name": "audio_set_volume",
        "description": "Ajusta el volumen del sistema y desactiva el mute.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "percent": {
                    "type": "integer",
                    "description": "Porcentaje de volumen (0 a 150)."
                },
                "unmute": {
                    "type": "boolean",
                    "description": "Desactivar silencio automaticamente (default: true)."
                }
            },
            "required": ["percent"]
        }
    },
    # ── Desktop Context Tools ──────────────────────────────
    {
        "name": "desktop_context_explain",
        "description": "Inspeccion contextual omnipotente: analiza que esta haciendo el usuario en pantalla (ventana activa o monitor), identifica botones y opciones visibles, y sugiere acciones proactivas con apoyo de documentacion local.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Objetivo de captura: 'active_window', 'all', 'monitor', 'bbox' (default: 'active_window')."
                },
                "user_intent": {
                    "type": "string",
                    "description": "Pregunta o intencion del usuario (default: '¿Que estoy haciendo y que opciones tengo?')."
                },
                "include_rag": {
                    "type": "boolean",
                    "description": "Consultar documentacion y guias locales (RAG) para sugerir pasos concretos (default: true)."
                }
            }
        }
    },
    {
        "name": "desktop_list_monitors",
        "description": "Lista todos los monitores y pantallas fisicas conectadas, sus resoluciones y geometrias.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "desktop_list_windows",
        "description": "Lista todas las ventanas abiertas en el escritorio, titulos de aplicaciones, geometrias y cual tiene el foco.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "desktop_capture_region",
        "description": "Captura una ventana, monitor o region rectangular de la pantalla y la guarda en la carpeta multimedia.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": "Tipo de objetivo: 'active_window', 'monitor', 'window', 'bbox', 'all' (default: 'active_window')."
                },
                "monitor_name": {
                    "type": "string",
                    "description": "Nombre del monitor si target='monitor' (ej: 'DP-2', 'eDP-1')."
                },
                "window_id": {
                    "type": "string",
                    "description": "ID de la ventana si target='window'."
                },
                "bbox": {
                    "type": "object",
                    "description": "Coordenadas {x, y, width, height} si target='bbox'."
                }
            }
        }
    },
    # ── Handy Integration ──────────────────────────────────
    {
        "name": "handy_status",
        "description": "Obtiene el estado de la integracion con Handy (cjpais/Handy), modelo Parakeet V3 y ultima transcripcion capturada.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "handy_toggle_transcription",
        "description": "Inicia o detiene la captura/transcripcion de audio global en la aplicacion Handy.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
]

# ── Handlers ───────────────────────────────────────────────


def _voice_speak(args):
    text = args.get("text", "")
    interruptible = args.get("interruptible", True)
    notify = args.get("notify", True)
    try:
        from scripts.voice.full_duplex_engine import FullDuplexVoiceEngine
        engine = FullDuplexVoiceEngine()
        res = engine.speak(text=text, interruptible=interruptible, notify=notify)
        if res.get("success"):
            engine_name = res.get("engine", "TTS")
            inter_str = " (interrumpible si hablas)" if interruptible else ""
            return f"Voz sintetizada y reproduciendo ({engine_name}):\n\"{text}\"{inter_str}"
        else:
            return f"Error al sintetizar voz: {res.get('error')}"
    except Exception as e:
        return f"Error en sintesis de voz: {e}"


def _voice_listen(args):
    timeout_seconds = args.get("timeout_seconds", 8.0)
    silence_ms = args.get("silence_ms", 800)
    try:
        from scripts.voice.full_duplex_engine import FullDuplexVoiceEngine
        engine = FullDuplexVoiceEngine()
        res = engine.listen(timeout_seconds=timeout_seconds, silence_ms=silence_ms)
        if res.get("success"):
            return f"Audio Capturado y Transcrito:\n\"{res.get('transcription', '')}\""
        else:
            return f"Error al escuchar microfono: {res.get('error')}"
    except Exception as e:
        return f"Error en escucha por voz: {e}"


def _voice_status(args):
    try:
        from scripts.voice.full_duplex_engine import FullDuplexVoiceEngine
        engine = FullDuplexVoiceEngine()
        st = engine.get_status()
        output = "Estado del Subsistema de Voz (Full-Duplex & Barge-In):\n\n"
        output += f"- Barge-In (Interrupcion activa): {'Activado' if st['barge_in_active'] else 'Desactivado'}\n"
        output += f"- Motor TTS: {st.get('tts_engine', 'none')} ({'Listo' if st['tts_ready'] else 'No disponible'})\n"
        output += f"- Whisper STT: {'Activo (:9093)' if st['stt_whisper_ready'] else 'Inactivo'}\n"
        output += f"- Microfono: {'Disponible' if st['microphone_ready'] else 'No detectado'}\n"
        output += f"- Reproductor: {'Listo (PipeWire)' if st['playback_ready'] else 'No detectado'}\n"
        return output
    except Exception as e:
        return f"Error al consultar estado de voz: {e}"


def _voice_set_profile(args):
    profile_id = args.get("profile_id", "")
    language = args.get("language")
    speed = args.get("speed")
    pitch = args.get("pitch")
    volume = args.get("volume")
    try:
        from scripts.voice.voice_profiles import VoiceProfileManager
        mgr = VoiceProfileManager()
        prof = mgr.set_profile(profile_id=profile_id, language=language, speed=speed, pitch=pitch, volume=volume)
        return f"Perfil de Voz Actualizado Exitosamente:\n- Perfil: `{prof['name']}` (`{prof['profile_id']}`)\n- Idioma / Acento: `{prof['language']}`\n- Velocidad: {prof['speed']}x\n- Tono (Pitch): {prof['pitch']}x\n- Volumen: {prof['volume']}%\n- Motor: `{prof['engine']}`"
    except Exception as e:
        return f"Error al configurar perfil de voz: {e}"


def _voice_list_profiles(args):
    try:
        from scripts.voice.voice_profiles import VoiceProfileManager
        mgr = VoiceProfileManager()
        profiles = mgr.list_available_profiles()
        output = "Perfiles de Voz y Acentos Disponibles:\n\n"
        for p in profiles:
            act = " (Activo)" if p.get("is_active") else ""
            output += f"- `{p['id']}`: {p['name']} ({p['language']}){act}\n  Motor: `{p['engine']}` | Velocidad: {p['speed']}x | Tono: {p['pitch']}x\n"
        return output.strip()
    except Exception as e:
        return f"Error al listar perfiles de voz: {e}"


def _voice_conversational_turn(args):
    prompt = args.get("prompt")
    try:
        from scripts.voice.conversational_loop import ConversationalVoiceLoop
        loop = ConversationalVoiceLoop(single_shot=True)
        if prompt:
            loop.query_llm(prompt)
        res = loop.run_turn()
        return "Turno Conversacional Completado. (Voz reproducida con Barge-In activo)."
    except Exception as e:
        return f"Error en turno conversacional: {e}"


def _voice_transcribe_audio(args):
    file_path = args.get("file_path", "")
    engine = args.get("engine", "auto")
    try:
        from pathlib import Path
        p = Path(file_path).expanduser().resolve()
        if not p.exists():
            return f"Archivo no encontrado: `{file_path}`"

        if engine.lower() == "parakeet":
            from scripts.voice.parakeet_engine import ParakeetEngine
            parakeet = ParakeetEngine()
            res = parakeet.transcribe(p)
            if res.get("success"):
                return f"Transcripcion (Parakeet V3 - {res.get('latency_ms')}ms):\n\n\"{res.get('text')}\""
            else:
                return f"Error en Parakeet: {res.get('error')}"

        from scripts.voice.full_duplex_engine import FullDuplexVoiceEngine
        engine_inst = FullDuplexVoiceEngine()
        text = engine_inst.transcribe_file(p)
        return f"Transcripcion (Motor ASR Hibrido):\n\n\"{text}\""
    except Exception as e:
        return f"Error al transcribir audio: {e}"


def _vision_analyze_image(args):
    image_path = args.get("image_path", "")
    prompt = args.get("prompt", "Describe esta imagen en detalle y extrae los datos clave.")
    try:
        from scripts.vision.multimodal_vision import MultimodalVisionEngine
        engine = MultimodalVisionEngine()
        return engine.analyze_image(image_path=image_path, prompt=prompt)
    except Exception as e:
        return f"Error en analisis visual: {e}"


def _vision_inspect_screen(args):
    prompt = args.get("prompt", "Analiza la actividad y elementos presentes en la pantalla.")
    try:
        from scripts.vision.multimodal_vision import MultimodalVisionEngine
        engine = MultimodalVisionEngine()
        res = engine.inspect_screen(prompt=prompt)
        output = f"Captura de Pantalla Realizada: `{res['filename']}`\n\n"
        output += res["analysis"]
        return output
    except Exception as e:
        return f"Error al inspeccionar pantalla: {e}"


def _vision_ocr(args):
    image_path = args.get("image_path", "")
    try:
        from scripts.vision.multimodal_vision import MultimodalVisionEngine
        engine = MultimodalVisionEngine()
        ocr_text = engine.run_ocr(image_path=image_path)
        if not ocr_text:
            return "No se detecto texto legible en la imagen."
        return f"Texto Extraido (OCR):\n```\n{ocr_text}\n```"
    except Exception as e:
        return f"Error al ejecutar OCR: {e}"


def _audio_list_devices(args):
    try:
        result = subprocess.run(
            ["pactl", "list", "sinks", "short"],
            capture_output=True, text=True, timeout=5
        )

        output = ["Dispositivos de salida:\n"]
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split()
                    output.append(f"  - {parts[1]} (State: {parts[2]})")

        result = subprocess.run(
            ["pactl", "list", "sources", "short"],
            capture_output=True, text=True, timeout=5
        )

        output.append("\nDispositivos de entrada:\n")
        if result.returncode == 0:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    parts = line.split()
                    output.append(f"  - {parts[1]} (State: {parts[2]})")

        return "\n".join(output)

    except Exception as e:
        return f"Error listando dispositivos de audio: {e}"


def _audio_set_source(args):
    sink = args.get("sink", "")
    try:
        result = subprocess.run(
            ["pactl", "set-default-sink", sink],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            return f"Error cambiando sink: {result.stderr}"

        log_operation("audio_set_source", {"sink": sink}, "changed")
        return f"Sink cambiado a: {sink}"

    except Exception as e:
        return f"Error cambiando sink: {e}"


def _audio_set_source_input(args):
    source = args.get("source", "")
    try:
        result = subprocess.run(
            ["pactl", "set-default-source", source],
            capture_output=True, text=True, timeout=5
        )

        if result.returncode != 0:
            return f"Error cambiando source: {result.stderr}"

        log_operation("audio_set_source_input", {"source": source}, "changed")
        return f"Source cambiado a: {source}"

    except Exception as e:
        return f"Error cambiando source: {e}"


def _audio_check_volume(args):
    min_volume = args.get("min_volume", 15)
    notify_if_inaudible = args.get("notify_if_inaudible", True)
    try:
        from scripts.voice.audio_diagnostics import AudioDiagnostics
        info = AudioDiagnostics.get_output_volume()
        audible, reason = AudioDiagnostics.check_audibility(min_volume=min_volume, notify_if_inaudible=notify_if_inaudible)
        mute_str = "Si (Muteado)" if info["is_muted"] else "No"
        icon = "OK" if audible else "WARNING"
        return f"{icon} Diagnostico de Volumen del Sistema:\n- Volumen: {info['volume_percent']}%\n- Silenciado (Mute): {mute_str}\n- Backend: `{info['backend']}`\n- Estado: {reason}"
    except Exception as e:
        return f"Error al diagnosticar audio: {e}"


def _audio_set_volume(args):
    percent = args.get("percent", 0)
    unmute = args.get("unmute", True)
    try:
        from scripts.voice.audio_diagnostics import AudioDiagnostics
        res = AudioDiagnostics.set_volume(percent=percent, unmute=unmute)
        if res.get("success"):
            return f"Volumen Ajustado al {res['volume_percent']}% (Mute desactivado: {res['unmuted']})."
        else:
            return f"Error al ajustar volumen: {res.get('error')}"
    except Exception as e:
        return f"Error al ajustar volumen: {e}"


def _desktop_context_explain(args):
    target = args.get("target", "active_window")
    user_intent = args.get("user_intent", "¿Que estoy haciendo y que opciones tengo?")
    include_rag = args.get("include_rag", True)
    try:
        from scripts.vision.desktop_context_engine import DesktopContextEngine
        engine = DesktopContextEngine()
        res = engine.explain_context(target=target, user_intent=user_intent, include_rag=include_rag)
        return res["report"]
    except Exception as e:
        return f"Error en inspeccion contextual de escritorio: {e}"


def _desktop_list_monitors(args):
    try:
        from scripts.vision.desktop_context_engine import DesktopContextEngine
        engine = DesktopContextEngine()
        monitors = engine.list_monitors()
        if not monitors:
            return "No se detectaron salidas de monitor activas (xrandr)."
        output = f"Monitores Detectados ({len(monitors)}):\n\n"
        for idx, m in enumerate(monitors, 1):
            prim = " (Principal)" if m.get("is_primary") else ""
            output += f"{idx}. `{m['name']}` - {m['width']}x{m['height']} (Offset: +{m['x']}+{m['y']}){prim}\n"
        return output.strip()
    except Exception as e:
        return f"Error al listar monitores: {e}"


def _desktop_list_windows(args):
    try:
        from scripts.vision.desktop_context_engine import DesktopContextEngine
        engine = DesktopContextEngine()
        windows = engine.list_windows()
        if not windows:
            return "No se encontraron ventanas abiertas en el entorno grafico."
        output = f"Ventanas Abiertas ({len(windows)}):\n\n"
        for idx, w in enumerate(windows, 1):
            foc = " (En foco / activa)" if w.get("is_focused") else ""
            output += f"{idx}. `[{w.get('app_class', 'App')}]` **{w.get('title', '(sin titulo)')}**{foc}\n   ID: `{w['window_id']}` | PID: {w.get('pid', 'N/A')}\n"
        return output.strip()
    except Exception as e:
        return f"Error al listar ventanas: {e}"


def _desktop_capture_region(args):
    target = args.get("target", "active_window")
    monitor_name = args.get("monitor_name")
    window_id = args.get("window_id")
    bbox = args.get("bbox")
    try:
        from scripts.vision.desktop_context_engine import DesktopContextEngine
        engine = DesktopContextEngine()
        shot_path = engine.capture_target(target=target, monitor_name=monitor_name, window_id=window_id, bbox=bbox)
        return f"Captura de Region Exitosa:\n- Objetivo: `{target}`\n- Archivo: `{shot_path.name}`\n- Ruta local: `{shot_path}`\n\nTip: Usa `media_view(file_path='{shot_path}')` para visualizar la imagen directamente en el chat."
    except Exception as e:
        return f"Error al capturar region de escritorio: {e}"


def _handy_status(args):
    try:
        from scripts.voice.handy_bridge import HandyBridge
        status = HandyBridge().get_status()
        daemon_str = "En ejecucion" if status.get("daemon_running") else "Detenido"
        parakeet_str = "Listo / Instalado" if status.get("parakeet_v3_ready") else "No encontrado"
        latest = status.get("latest_transcript") or "(Ninguna en esta sesion)"
        rec = status.get("latest_recording") or "(Ninguna)"
        return (
            f"Estado de Integracion Handy (cjpais/Handy):\n"
            f"- Demonio / App Handy: {daemon_str}\n"
            f"- Modelo Parakeet V3: {parakeet_str}\n"
            f"- Ultima Transcripcion: \"{latest}\"\n"
            f"- Ultima Grabacion: `{rec}`"
        )
    except Exception as e:
        return f"Error al consultar estado de Handy: {e}"


def _handy_toggle_transcription(args):
    try:
        from scripts.voice.handy_bridge import HandyBridge
        res = HandyBridge().toggle_transcription()
        if res.get("success"):
            return "Senal enviada a Handy: Grabacion / transcripcion conmutada con exito."
        else:
            return f"No se pudo conmutar Handy: {res.get('error')}"
    except Exception as e:
        return f"Error al conmutar Handy: {e}"


HANDLERS = {
    "voice_speak": _voice_speak,
    "voice_listen": _voice_listen,
    "voice_status": _voice_status,
    "voice_set_profile": _voice_set_profile,
    "voice_list_profiles": _voice_list_profiles,
    "voice_conversational_turn": _voice_conversational_turn,
    "voice_transcribe_audio": _voice_transcribe_audio,
    "vision_analyze_image": _vision_analyze_image,
    "vision_inspect_screen": _vision_inspect_screen,
    "vision_ocr": _vision_ocr,
    "audio_list_devices": _audio_list_devices,
    "audio_set_source": _audio_set_source,
    "audio_set_source_input": _audio_set_source_input,
    "audio_check_volume": _audio_check_volume,
    "audio_set_volume": _audio_set_volume,
    "desktop_context_explain": _desktop_context_explain,
    "desktop_list_monitors": _desktop_list_monitors,
    "desktop_list_windows": _desktop_list_windows,
    "desktop_capture_region": _desktop_capture_region,
    "handy_status": _handy_status,
    "handy_toggle_transcription": _handy_toggle_transcription,
}
