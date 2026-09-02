#!/usr/bin/env python3
"""
AI Lab — Context & Conversation Compaction Engine (Rolling Epistemic Summarizer)
Provee compresión inteligente de historial conversacional sin pérdida de contexto:
  - Mantiene intactos los turnos recientes (alta fidelidad).
  - Compacta turnos antiguos en un 'Epistemic State Digest' estructurado (Metas, Decisiones, Variables y Progreso).
  - Ejecuta la compresión en el sub-agente E4B (:9091 en CPU) sin tocar la VRAM de la GPU.
  - Fallback extractivo garantizado (0 caídas).
"""

import os
import sys
import json
import re
import urllib.request
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

E4B_ENDPOINT = "http://127.0.0.1:9091/v1/chat/completions"
GEMMA_ENDPOINT = "http://127.0.0.1:9090/v1/chat/completions"


class ContextCompactor:
    """Motor de compactación jerárquica de contexto conversacional."""

    def __init__(
        self,
        primary_endpoint: str = E4B_ENDPOINT,
        fallback_endpoint: str = GEMMA_ENDPOINT,
        timeout_seconds: float = 12.0
    ):
        self.primary_endpoint = primary_endpoint
        self.fallback_endpoint = fallback_endpoint
        self.timeout = timeout_seconds

    @staticmethod
    def estimate_tokens(text: str) -> int:
        """Estimación rápida y precisa de tokens para texto en español/inglés."""
        if not text:
            return 0
        # Promedio de 3.6 caracteres por token en modelos multilingües
        return max(1, int(len(text) / 3.6))

    @staticmethod
    def estimate_history_tokens(messages: List[Dict[str, Any]]) -> int:
        """Calcula los tokens totales aproximados en una lista de mensajes."""
        total = 0
        for m in messages:
            content = m.get("content") or ""
            if not isinstance(content, str):
                content = json.dumps(content)
            total += ContextCompactor.estimate_tokens(content)
            
            # Sumar reasoning si existe
            thinking = m.get("thinking") or m.get("reasoning_content") or ""
            if thinking:
                total += ContextCompactor.estimate_tokens(str(thinking))
        return total

    def should_compact(
        self,
        messages: List[Dict[str, Any]],
        max_turns: int = 10,
        max_tokens: int = 6000
    ) -> bool:
        """Determina si una conversación amerita compactación."""
        if len(messages) <= max_turns:
            return False
        if self.estimate_history_tokens(messages) > max_tokens:
            return True
        return len(messages) > max_turns

    def compact_conversation(
        self,
        messages: List[Dict[str, Any]],
        max_recent: int = 6,
        existing_digest: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Divide los mensajes en recientes (sin modificar) y antiguos (compactados).
        Retorna el historial ensamblado y estadísticas de ahorro.
        """
        # Excluir mensaje de sistema inicial si existe
        user_or_asst_msgs = [m for m in messages if m.get("role") in ("user", "assistant", "tool")]
        
        if len(user_or_asst_msgs) <= max_recent:
            return {
                "compacted": False,
                "summary": existing_digest,
                "assembled_messages": messages,
                "token_savings_percent": 0.0,
                "original_tokens": self.estimate_history_tokens(messages),
                "compacted_tokens": self.estimate_history_tokens(messages)
            }

        older_msgs = user_or_asst_msgs[:-max_recent]
        recent_msgs = user_or_asst_msgs[-max_recent:]

        original_tokens = self.estimate_history_tokens(messages)

        # Generar resumen estructurado de los mensajes antiguos
        digest = self._generate_epistemic_digest(older_msgs, existing_digest)

        compaction_anchor = {
            "role": "system",
            "content": (
                "### 📦 CONTEXTO COMPACTADO DE LA CONVERSACIÓN PREVIA (Memoria de Trabajo Activa):\n"
                f"{digest}\n"
                "---\n"
                "*Nota: Los turnos anteriores fueron compactados para optimizar la atención y coherencia. "
                "Usa este digest como base factual y continúa con los turnos recientes a continuación.*"
            )
        }

        # Ensamblar: Ancla compactada + Turnos recientes
        assembled = [compaction_anchor] + recent_msgs
        compacted_tokens = self.estimate_history_tokens(assembled)
        savings = max(0.0, round(((original_tokens - compacted_tokens) / original_tokens) * 100, 1))

        return {
            "compacted": True,
            "summary": digest,
            "assembled_messages": assembled,
            "token_savings_percent": savings,
            "original_tokens": original_tokens,
            "compacted_tokens": compacted_tokens,
            "compacted_turns_count": len(older_msgs)
        }

    def _generate_epistemic_digest(
        self,
        older_messages: List[Dict[str, Any]],
        existing_digest: Optional[str] = None
    ) -> str:
        """Invoca a E4B (o fallback) para generar el digest estructurado."""
        dialogue_transcript = []
        for m in older_messages:
            role_name = "👤 Usuario" if m.get("role") == "user" else "🤖 Asistente"
            content = m.get("content", "")
            if not isinstance(content, str):
                content = json.dumps(content)
            dialogue_transcript.append(f"{role_name}: {content}")

        transcript_text = "\n\n".join(dialogue_transcript)
        
        prompt = (
            "Eres el motor de compactación y síntesis de memoria conversacional de AI Lab.\n"
            "Tu tarea es analizar los turnos anteriores de la conversación y extraer un 'Digest Epistémico' ultra-preciso y conciso en español.\n\n"
        )
        if existing_digest:
            prompt += f"Digest previo existente:\n{existing_digest}\n\n"

        prompt += (
            f"Nuevos turnos a compactar:\n{transcript_text}\n\n"
            "Estructura obligatoria de tu respuesta:\n"
            "🎯 **Objetivo / Tarea Principal**: (1-2 oraciones del objetivo central)\n"
            "🔑 **Decisiones y Acuerdos**: (Puntos clave acordados, preferencias confirmadas o restricciones fijadas)\n"
            "📌 **Entidades, Rutas y Variables**: (Nombres, rutas de archivos, puertos, servicios o comandos mencionados)\n"
            "🛠️ **Estado Actual y Progreso**: (Qué se resolvió y qué queda pendiente)\n"
            "Responde directamente con la estructura anterior sin introducciones ni saludos."
        )

        payload = {
            "model": "default",
            "messages": [
                {"role": "system", "content": "Eres un sintetizador técnico conciso."},
                {"role": "user", "content": prompt}
            ],
            "max_tokens": 500,
            "temperature": 0.3
        }

        # Intento 1: E4B (:9091)
        res = self._call_llm_api(self.primary_endpoint, payload)
        if res:
            return res.strip()

        # Intento 2: Fallback Gemma (:9090)
        res = self._call_llm_api(self.fallback_endpoint, payload)
        if res:
            return res.strip()

        # Intento 3: Fallback Heurístico Local (100% garantizado)
        return self._extractive_fallback_digest(older_messages, existing_digest)

    def _call_llm_api(self, url: str, payload: dict) -> Optional[str]:
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                choice = data["choices"][0]["message"]
                return choice.get("content", "").strip()
        except Exception:
            return None

    def _extractive_fallback_digest(
        self,
        older_messages: List[Dict[str, Any]],
        existing_digest: Optional[str] = None
    ) -> str:
        """Generador heurístico de respaldo en caso de que los endpoints no respondan."""
        user_msgs = [m.get("content", "") for m in older_messages if m.get("role") == "user"]
        
        topics = []
        for text in user_msgs[:4]:
            first_line = text.strip().split("\n")[0]
            if len(first_line) > 5:
                topics.append(f"• {first_line[:80]}")

        digest_lines = [
            "🎯 **Objetivo / Temas Tratados**:",
            "\n".join(topics) if topics else "• Conversación técnica general sobre el sistema.",
            "",
            "🛠️ **Estado y Continuidad**:",
            f"• Se compactaron {len(older_messages)} turnos previos para preservar coherencia contextual."
        ]

        if existing_digest:
            digest_lines.insert(0, f"*(Digest previo integrado)*:\n{existing_digest}\n")

        return "\n".join(digest_lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI Lab — Demostración de Context Compactor")
    parser.add_argument("--test", action="store_true", help="Ejecutar prueba con conversación simulada")
    args = parser.parse_args()

    compactor = ContextCompactor()

    if args.test:
        print("\n🧪 [Prueba de Context Compaction]")
        fake_conversation = [
            {"role": "user", "content": "Hola, quiero configurar un servidor de base de datos PostgreSQL en el puerto 5432."},
            {"role": "assistant", "content": "Entendido. Para Pop!_OS podemos instalar postgresql y crear la base de datos 'ailab_db'."},
            {"role": "user", "content": "Perfecto, el usuario debe llamarse 'darkseid' con contraseña 'pathetique'."},
            {"role": "assistant", "content": "Listo, usuario darkseid creado y permisos asignados a ailab_db."},
            {"role": "user", "content": "Ahora quiero que configuremos un script en Python para conectarnos con psycopg2."},
            {"role": "assistant", "content": "Aquí tienes el script db_connector.py configurado con tus credenciales."},
            {"role": "user", "content": "Oye, ¿podemos cambiar la tabla para incluir una columna de timestamps?"},
            {"role": "assistant", "content": "Sí, añadida la columna created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP."},
            {"role": "user", "content": "Bien, ahora pruébalo insertando un registro."},
            {"role": "assistant", "content": "Registro insertado exitosamente con ID 1."},
            {"role": "user", "content": "¿En qué puerto dijimos que estaba corriendo?"}
        ]

        print(f"📊 Mensajes originales: {len(fake_conversation)}")
        print(f"🧮 Tokens estimados originales: {compactor.estimate_history_tokens(fake_conversation)}")

        result = compactor.compact_conversation(fake_conversation, max_recent=3)

        print(f"\n📦 ¿Se compactó?: {result['compacted']}")
        print(f"📉 Ahorro de Tokens: {result['token_savings_percent']}%")
        print(f"🧮 Tokens compactados: {result['compacted_tokens']} (de {result['original_tokens']})")
        print(f"\n📝 Digest Generado:\n{result['summary']}")
        print("\n📜 Mensajes Ensamblados Finales:")
        for idx, m in enumerate(result["assembled_messages"]):
            print(f" [{idx}] {m['role'].upper()}: {m['content'][:90]}...")


if __name__ == "__main__":
    main()
