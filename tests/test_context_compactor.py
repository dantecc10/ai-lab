#!/usr/bin/env python3
"""
AI Lab — Pruebas unitarias para Context & Conversation Compaction Engine.
"""

import unittest
from scripts.tools.context_compactor import ContextCompactor


class TestContextCompactor(unittest.TestCase):

    def setUp(self):
        # Usar puertos ficticios para validar resiliencia del fallback heurístico
        self.compactor = ContextCompactor(
            primary_endpoint="http://127.0.0.1:9998/v1/chat/completions",
            fallback_endpoint="http://127.0.0.1:9999/v1/chat/completions",
            timeout_seconds=0.5
        )

    def test_token_estimation(self):
        text = "Esta es una prueba de estimación de tokens para AI Lab."
        tokens = self.compactor.estimate_tokens(text)
        self.assertGreater(tokens, 5)
        self.assertLess(tokens, 30)

    def test_short_conversation_no_compaction(self):
        short_conv = [
            {"role": "user", "content": "Hola"},
            {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"}
        ]
        res = self.compactor.compact_conversation(short_conv, max_recent=4)
        self.assertFalse(res["compacted"])
        self.assertEqual(len(res["assembled_messages"]), 2)

    def test_long_conversation_compaction_with_fallback(self):
        long_conv = [
            {"role": "user", "content": f"Paso {i}: Configurar el módulo {i} del sistema"} 
            for i in range(1, 15)
        ]
        res = self.compactor.compact_conversation(long_conv, max_recent=4)
        self.assertTrue(res["compacted"])
        self.assertIn("🎯 **Objetivo / Temas Tratados**", res["summary"])
        # Debe contener 1 mensaje de sistema (ancla compactada) + 4 mensajes recientes
        self.assertEqual(len(res["assembled_messages"]), 5)
        self.assertEqual(res["assembled_messages"][0]["role"], "system")
        self.assertIn("CONTEXTO COMPACTADO", res["assembled_messages"][0]["content"])

    def test_should_compact_thresholds(self):
        short_conv = [{"role": "user", "content": "Test"}] * 3
        long_conv = [{"role": "user", "content": "Test"}] * 15
        self.assertFalse(self.compactor.should_compact(short_conv, max_turns=10))
        self.assertTrue(self.compactor.should_compact(long_conv, max_turns=10))


if __name__ == "__main__":
    unittest.main()
