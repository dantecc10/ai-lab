#!/usr/bin/env python3
"""
AI Lab — Autonomous Conversational Voice Loop (Hands-Free Assistant)
Bucle de conversación por voz continua: escucha VAD -> transcripción Whisper ->
razonamiento Gemma 4 / Local LLM -> síntesis Piper/spd-say con interrupción (Barge-In).
"""

import os
import sys
import time
import json
import signal
import argparse
import urllib.request
from pathlib import Path

# Asegurar que la raíz del proyecto ai-lab esté en sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

LLAMA_ENDPOINT = "http://127.0.0.1:9090/v1/chat/completions"

def get_system_prompt() -> str:
    from datetime import datetime
    now_str = datetime.now().strftime("%A %d de %B de %Y, %H:%M")
    return (
        f"Eres el asistente de voz inteligente de AI Lab en Pop!_OS. "
        f"Fecha y hora actual: {now_str}. "
        "Instrucción fundamental: Responde directamente al usuario en español con 1 o 2 oraciones breves, útiles y concisas para ser sintetizadas por voz. "
        "No uses bloques de pensamiento, ni borradores, ni texto en inglés."
    )

class ConversationalVoiceLoop:
    """Bucle conversacional continuo manos libres por voz."""

    def __init__(self, endpoint: str = LLAMA_ENDPOINT, single_shot: bool = False):
        self.endpoint = endpoint
        self.single_shot = single_shot
        self.history: list[dict] = [{"role": "system", "content": get_system_prompt()}]
        self.last_assistant_reply: str = ""
        self.running = True

    def is_self_echo(self, user_transcript: str) -> bool:
        """Detecta si la transcripción capturada proviene del audio emitido por las bocinas."""
        if not user_transcript or not self.last_assistant_reply:
            return False
        import difflib, re
        
        def normalize(s: str) -> str:
            return re.sub(r"[^\w\s]", "", s.lower()).strip()
            
        u = normalize(user_transcript)
        a = normalize(self.last_assistant_reply)
        if not u or not a:
            return False
            
        if u in a or a in u:
            return True
            
        ratio = difflib.SequenceMatcher(None, u, a).ratio()
        if ratio >= 0.50:
            return True
            
        u_words = set(u.split())
        a_words = set(a.split())
        if len(u_words) >= 2 and len(u_words.intersection(a_words)) / len(u_words) >= 0.60:
            return True
            
        return False

    def query_llm(self, user_text: str) -> str:
        """Envía el texto al modelo local Gemma 4 y obtiene la respuesta final en español."""
        self.history.append({"role": "user", "content": user_text})
        
        # Refrescar prompt del sistema con fecha/hora actual y contexto JIT (Directivas + Grafo)
        sys_prompt = get_system_prompt()
        try:
            from scripts.tools.knowledge_graph import KnowledgeGraphEngine
            kg = KnowledgeGraphEngine()
            jit_context = kg.format_jit_context_block(user_text)
            if jit_context:
                sys_prompt += f"\n\n{jit_context}"
        except Exception:
            pass

        self.history[0] = {"role": "system", "content": sys_prompt}
        
        # Context Compaction en el bucle de voz para mantener memoria sin saturación
        try:
            from scripts.tools.context_compactor import ContextCompactor
            compactor = ContextCompactor()
            if len(self.history) > 6:
                compact_res = compactor.compact_conversation(self.history[1:], max_recent=4)
                voice_messages = [self.history[0]] + compact_res["assembled_messages"]
            else:
                voice_messages = self.history
        except Exception:
            voice_messages = self.history[-6:]

        payload = {
            "model": "default",
            "messages": voice_messages,
            "max_tokens": 600,
            "temperature": 0.6
        }

        try:
            req = urllib.request.Request(
                self.endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=50.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]["message"]
                reply = choice.get("content", "").strip()

                if not reply:
                    reply = "He recibido tu consulta, ¿deseas que profundice en algún aspecto?"

                self.history.append({"role": "assistant", "content": reply})
                return reply
        except Exception as e:
            return f"Lo siento, ocurrió un problema al interactuar con el modelo local: {e}"

    def run_turn(self) -> bool:
        """Ejecuta un turno de conversación (Escuchar -> Pensar -> Hablar)."""
        from scripts.voice.full_duplex_engine import FullDuplexVoiceEngine
        from scripts.voice.audio_diagnostics import AudioDiagnostics

        # Asegurar ganancia óptima del micrófono y salida de audio
        AudioDiagnostics.ensure_microphone_gain(85)
        audible, reason = AudioDiagnostics.check_audibility(min_volume=15, notify_if_inaudible=True)
        if not audible:
            print(f"\n[!] Advertencia de Audio: {reason}")

        engine = FullDuplexVoiceEngine()

        print("\n🎙️ [Escuchando micrófono...] (Habla ahora)")
        listen_res = engine.listen(timeout_seconds=6.0, silence_ms=700)
        
        if not listen_res.get("success") or not listen_res.get("transcription"):
            print("⏳ [Silencio detectado]")
            return True

        user_text = listen_res["transcription"].strip()

        # Filtro de Eco Propio (evitar que el asistente se responda a sí mismo)
        if self.is_self_echo(user_text):
            print(f"🛡️ [Eco de altavoces detectado y descartado]: \"{user_text}\"")
            return True

        print(f"👤 [Tú]: {user_text}")

        # Comandos de salida
        if user_text.lower() in ["adiós", "salir", "terminar", "apágate", "stop", "exit"]:
            farewell = "Hasta luego. Asistente en reposo."
            print(f"🤖 [Asistente]: {farewell}")
            engine.speak(farewell, interruptible=False, block=True)
            return False

        # 2. Inferencia con LLM
        print("🧠 [Pensando respuesta...]")
        reply = self.query_llm(user_text)
        self.last_assistant_reply = reply
        print(f"🤖 [Asistente]: {reply}")

        # 3. Síntesis y habla bloqueante para evitar solapamiento con el micrófono
        engine.speak(reply, interruptible=True, notify=True, block=True)

        if self.single_shot:
            return False

        return True

    def start(self):
        """Inicia el bucle conversacional continuo."""
        print("=" * 60)
        print("🎙️ AI LAB — ASISTENTE DE VOZ CONTINUO (FULL-DUPLEX)")
        print("• Habla de forma natural; el asistente detecta silencios (VAD).")
        print("• Si el asistente está hablando y comienzas a hablar, se interrumpirá (Barge-In).")
        print("• Presiona Ctrl+C o di 'adiós' para salir.")
        print("=" * 60)

        def handle_sigint(sig, frame):
            self.running = False
            print("\n[+] Bucle de voz finalizado.")
            sys.exit(0)

        signal.signal(signal.SIGINT, handle_sigint)

        while self.running:
            try:
                should_continue = self.run_turn()
                if not should_continue:
                    break
            except KeyboardInterrupt:
                break
            except Exception as e:
                print(f"[!] Error en turno de voz: {e}")
                time.sleep(2.0)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Asistente conversacional por voz continuo")
    parser.add_argument("--single", action="store_true", help="Ejecuta un único turno de conversación y sale.")
    args = parser.parse_args()

    loop = ConversationalVoiceLoop(single_shot=args.single)
    loop.start()
