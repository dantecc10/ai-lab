#!/usr/bin/env python3
"""
Pruebas unitarias para KnowledgeGraphEngine y resolución JIT de memoria cognitiva.
"""

import unittest
import tempfile
from pathlib import Path
from scripts.tools.knowledge_graph import KnowledgeGraphEngine, normalize_term


class TestKnowledgeGraph(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_kg.db"
        self.kg = KnowledgeGraphEngine(db_path=self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_term_normalization(self):
        self.assertEqual(normalize_term("José Miguel Martínez"), "jose miguel martinez")
        self.assertEqual(normalize_term('"el Capi"'), "el capi")
        self.assertEqual(normalize_term("Real Recursantes!"), "real recursantes")

    def test_save_entity_and_alias_resolution(self):
        eid = self.kg.save_entity(
            name="José Miguel Martínez",
            entity_type="person",
            summary="Mejor amigo del usuario y capitán de fútbol.",
            aliases=["Miguelito", "el Capi", "Pirinola", "Miguelonch"]
        )
        self.assertGreater(eid, 0)

        # Buscar por alias exacto
        ctx = self.kg.resolve_prompt_context("¿Dónde está el Capi?")
        entities = ctx["resolved_entities"]
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["name"], "José Miguel Martínez")
        self.assertIn("Pirinola", entities[0]["aliases"])

    def test_relations_creation_and_traversal(self):
        self.kg.save_entity("José Miguel", "person", "Capitán del equipo")
        self.kg.save_entity("Real Recursantes", "team", "Equipo de fútbol")
        ok = self.kg.add_relation("José Miguel", "CAPITAN_DE", "Real Recursantes", "Líder en la cancha")
        self.assertTrue(ok)

        ctx = self.kg.resolve_prompt_context("Háblame de Real Recursantes")
        entities = ctx["resolved_entities"]
        self.assertEqual(len(entities), 1)
        self.assertEqual(entities[0]["name"], "Real Recursantes")
        self.assertTrue(any("José Miguel" in str(r) for r in entities[0]["relations"]))

    def test_directives_management(self):
        did = self.kg.save_directive(
            directive="Fragmentación Atómica: Descomponer hechos en entidades.",
            category="methodology"
        )
        self.assertGreater(did, 0)

        directives = self.kg.list_active_directives()
        self.assertEqual(len(directives), 1)
        self.assertEqual(directives[0]["category"], "methodology")

        # JIT block format
        block = self.kg.format_jit_context_block("Mensaje sin entidades")
        self.assertIn("Fragmentación Atómica", block)
        self.assertNotIn("Entidades y Relaciones", block)


if __name__ == "__main__":
    unittest.main()
