#!/usr/bin/env python3
"""
AI Lab — Pruebas unitarias completas para Cognitive Memory Engine 2.0:
- Multi-Hop Traversal (2-Hop Graph)
- Memoria Temporal y Decaimiento TTL
- Auto-Consolidación Proactiva Heurística
- Topología de Infraestructura de Desarrollo
"""

import unittest
import tempfile
import sqlite3
from pathlib import Path
from scripts.tools.knowledge_graph import KnowledgeGraphEngine, normalize_term
from scripts.tools.auto_consolidator import MemoryAutoConsolidator


class TestCognitiveMemoryV2(unittest.TestCase):

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_kg_v2.db"
        self.kg = KnowledgeGraphEngine(db_path=self.db_path)
        self.consolidator = MemoryAutoConsolidator(kg=self.kg)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_multi_hop_traversal(self):
        # 1. Crear cadena: Alice -> AMIGO_DE -> Bob -> CAPITAN_DE -> CyberTeam
        self.kg.save_entity("Alice", "person", "Ingeniera de software", aliases=["Ali"])
        self.kg.save_entity("Bob", "person", "Capitán del equipo", aliases=["Bobby", "el Capi"])
        self.kg.save_entity("CyberTeam", "team", "Equipo de e-sports", aliases=["Cyber"])

        self.kg.add_relation("Alice", "AMIGO_DE", "Bob", "Amistad cercana")
        self.kg.add_relation("Bob", "CAPITAN_DE", "CyberTeam", "Líder del equipo")

        # Traversal 2-hop desde Alice
        res = self.kg.traverse_graph("Alice", max_hops=2)
        node_names = [n["name"] for n in res["nodes"]]
        self.assertIn("Alice", node_names)
        self.assertIn("Bob", node_names)
        self.assertIn("CyberTeam", node_names)

        # Traversal buscando por alias "Bobby"
        res_alias = self.kg.traverse_graph("Bobby", max_hops=1)
        self.assertEqual(res_alias["root"]["name"], "Bob")

    def test_temporal_memory_and_pruning(self):
        # Entidad permanente
        self.kg.save_entity("Familia", "concept", "Lazos familiares", is_permanent=True)
        # Entidad temporal vencida
        eid_temp = self.kg.save_entity("Tarea Temporal", "task", "Comprar leche hoy", is_permanent=False, decay_days=1)

        # Simular fecha pasada en SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("UPDATE entities SET last_accessed_at = '2020-01-01 00:00:00' WHERE id = ?", (eid_temp,))

        pruned = self.kg.prune_expired_entities()
        self.assertEqual(pruned, 1)

        # La permanente debe seguir existiendo
        ctx = self.kg.resolve_prompt_context("Háblame de la Familia")
        self.assertEqual(len(ctx["resolved_entities"]), 1)

    def test_auto_consolidation_heuristics(self):
        sample_messages = [
            {
                "role": "user",
                "content": "Rodrigo Gómez es mi compañero de trabajo. Suelo llamarle Rodri o 'el Inge'. Deberías siempre fragmentar las memorias."
            }
        ]

        res = self.consolidator.process_conversation_messages(sample_messages)
        self.assertGreaterEqual(len(res["entities_saved"]), 1)
        self.assertEqual(res["entities_saved"][0]["name"], "Rodrigo Gómez")
        self.assertIn("el Inge", res["entities_saved"][0]["aliases"])
        self.assertIn("Rodri", res["entities_saved"][0]["aliases"])

        self.assertGreaterEqual(len(res["directives_saved"]), 1)
        self.assertTrue(any("fragmentar" in d["directive"].lower() for d in res["directives_saved"]))

    def test_developer_infrastructure_seeding(self):
        self.kg.seed_developer_infrastructure()
        res = self.kg.traverse_graph("RTX 5060", max_hops=2)
        node_names = [n["name"] for n in res["nodes"]]
        self.assertIn("NVIDIA RTX 5060 Laptop GPU", node_names)
        self.assertIn("Gemma 4 Server", node_names)
        self.assertIn("Pop!_OS Host", node_names)


if __name__ == "__main__":
    unittest.main()
