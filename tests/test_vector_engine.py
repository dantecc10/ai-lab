#!/usr/bin/env python3
"""Pruebas unitarias para VectorEngine y RAG Semántico (Fase 3)."""

import unittest
import tempfile
from pathlib import Path
from scripts.tools.vector_engine import VectorEngine, TextEmbedder, DocumentChunker

class TestVectorEngine(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmpdir.name) / "test_vectors.db"
        self.engine = VectorEngine(db_path=self.db_path)

    def tearDown(self):
        self.tmpdir.cleanup()

    def test_embedder_normalization_and_similarity(self):
        embedder = TextEmbedder(dim=128)
        vec1 = embedder.embed_text("inteligencia artificial y modelos de lenguaje")
        vec2 = embedder.embed_text("sistemas de inteligencia artificial y modelos neuronales")
        vec3 = embedder.embed_text("receta culinaria de pastel dulce con fresas")

        self.assertEqual(len(vec1), 128)
        sim_ai = TextEmbedder.cosine_similarity(vec1, vec2)
        sim_cake = TextEmbedder.cosine_similarity(vec1, vec3)

        self.assertGreater(sim_ai, sim_cake, "Texto relacionado con IA debe ser más similar que receta")

    def test_markdown_chunker(self):
        md_text = """# Titulo Principal
Este es el inicio del documento sobre arquitectura de sistemas.

## Sección de Base de Datos
Aquí explicamos cómo funciona SQLite y los índices de búsqueda.

## Sección de Rendimiento
Optimizaciones para GPU y consumo de memoria.
"""
        chunks = DocumentChunker.chunk_markdown(md_text, max_chunk_size=100)
        self.assertGreaterEqual(len(chunks), 2)
        self.assertIn("SQLite", "\n".join(c["text"] for c in chunks))

    def test_index_file_and_semantic_search(self):
        sample_file = Path(self.tmpdir.name) / "doc_test.md"
        sample_file.write_text("""# Guía de Red
Instrucciones para configurar SSH en el puerto 2222 y túneles seguros.
""", encoding="utf-8")

        chunks_indexed = self.engine.index_file(sample_file, collection="infra")
        self.assertGreater(chunks_indexed, 0)

        results = self.engine.search_documents("puerto ssh y conexión segura", collection="infra", limit=2)
        self.assertGreater(len(results), 0)
        self.assertIn("SSH", results[0]["content"])
        self.assertGreater(results[0]["score"], 0.2)

    def test_episodic_memory_save_and_search(self):
        mem_id = self.engine.save_memory(
            "El usuario usa Arch Linux con GPU RTX 5060 y prefiere Bash",
            category="preference"
        )
        self.assertGreater(mem_id, 0)

        memories = self.engine.search_memories("¿Qué tarjeta gráfica tiene el usuario?", category="preference")
        self.assertGreater(len(memories), 0)
        self.assertIn("RTX 5060", memories[0]["content"])

    def test_get_stats(self):
        stats = self.engine.get_stats()
        self.assertIn("total_chunks", stats)
        self.assertIn("collections", stats)

if __name__ == "__main__":
    unittest.main()
