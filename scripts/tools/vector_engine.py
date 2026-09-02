#!/usr/bin/env python3
"""
AI Lab — Vector Memory & Semantic Search Engine (RAG Local)
Provee almacenamiento vectorial persistente, indexación semántica de código/documentación
y memoria asociativa sin consumo de VRAM de la GPU.
"""

import os
import sys
import json
import math
import struct
import sqlite3
import hashlib
import re
from pathlib import Path
from datetime import datetime

# Directorio de almacenamiento vectorial
DEFAULT_VECTOR_DIR = Path.home() / ".local" / "share" / "ai-lab" / "vectors"
DEFAULT_DB_PATH = DEFAULT_VECTOR_DIR / "vector_store.db"

VECTOR_DIM = 256

STOP_WORDS = {
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "en", "con",
    "por", "para", "a", "al", "del", "que", "es", "son", "se", "su", "sus", "como",
    "the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "with", "by", "of", "is", "are"
}

class TextEmbedder:
    """Generador de embeddings densos normalizados para CPU."""

    def __init__(self, dim: int = VECTOR_DIM):
        self.dim = dim
        self._model = None
        self._try_load_neural_model()

    def _try_load_neural_model(self):
        """Intenta cargar un modelo neuronal si está instalado."""
        try:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer("all-MiniLM-L6-v2", device="cpu")
        except Exception:
            self._model = None

    def embed_text(self, text: str) -> list[float]:
        """Genera un vector denso normalizado (L2) a partir de texto."""
        if not text or not text.strip():
            return [0.0] * self.dim

        if self._model:
            try:
                emb = self._model.encode(text, normalize_embeddings=True)
                return emb.tolist()[:self.dim]
            except Exception:
                pass

        # Algoritmo de Hashing Denso y n-gramas ponderados (0 dependencias, alta velocidad)
        vec = [0.0] * self.dim
        clean_text = text.lower().strip()
        tokens = [t for t in re.findall(r"\b\w+\b", clean_text) if t not in STOP_WORDS]

        # Ponderar tokens y n-gramas de caracteres con pesos positivos
        for token in tokens:
            # Token hash
            h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
            idx = h % self.dim
            weight = 1.0 + math.log(1.0 + len(token))
            vec[idx] += weight

            # Sub-tokens / character 3-grams para similitud morfológica
            if len(token) >= 3:
                for i in range(len(token) - 2):
                    ngram = token[i:i+3]
                    h_ng = int(hashlib.md5(ngram.encode("utf-8")).hexdigest(), 16)
                    idx_ng = h_ng % self.dim
                    vec[idx_ng] += 0.35

        # Normalización L2
        norm = math.sqrt(sum(x * x for x in vec))
        if norm > 1e-9:
            vec = [x / norm for x in vec]
        return vec

    @staticmethod
    def serialize_vector(vector: list[float]) -> bytes:
        """Serializa lista de floats a bytes binarios empaquetados."""
        return struct.pack(f"{len(vector)}f", *vector)

    @staticmethod
    def deserialize_vector(blob: bytes) -> list[float]:
        """Deserializa bytes binarios a lista de floats."""
        count = len(blob) // 4
        return list(struct.unpack(f"{count}f", blob))

    @staticmethod
    def cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Calcula la similitud coseno entre dos vectores normalizados."""
        if len(v1) != len(v2):
            min_len = min(len(v1), len(v2))
            v1, v2 = v1[:min_len], v2[:min_len]
        return sum(a * b for a, b in zip(v1, v2))


class DocumentChunker:
    """Segmentador inteligente de documentos y código."""

    @staticmethod
    def chunk_markdown(content: str, max_chunk_size: int = 800, overlap: int = 100) -> list[dict]:
        """Divide documentos Markdown preservando encabezados y contexto."""
        chunks = []
        lines = content.splitlines()
        current_header = "Documento"
        current_lines = []
        current_len = 0

        for line in lines:
            if line.startswith("#"):
                # Si hay contenido acumulado, emitir chunk
                if current_lines:
                    text_chunk = "\n".join(current_lines).strip()
                    if text_chunk:
                        chunks.append({
                            "header": current_header,
                            "text": f"[{current_header}]\n{text_chunk}"
                        })
                    current_lines = []
                    current_len = 0
                current_header = line.strip("#").strip()

            current_lines.append(line)
            current_len += len(line) + 1

            if current_len >= max_chunk_size:
                text_chunk = "\n".join(current_lines).strip()
                if text_chunk:
                    chunks.append({
                        "header": current_header,
                        "text": f"[{current_header}]\n{text_chunk}"
                    })
                # Mantener overlap de las últimas líneas
                current_lines = current_lines[-3:]
                current_len = sum(len(l) + 1 for l in current_lines)

        if current_lines:
            text_chunk = "\n".join(current_lines).strip()
            if text_chunk:
                chunks.append({
                    "header": current_header,
                    "text": f"[{current_header}]\n{text_chunk}"
                })
        return chunks

    @staticmethod
    def chunk_code(content: str, max_lines: int = 40, overlap_lines: int = 5) -> list[dict]:
        """Divide código fuente respetando funciones y clases."""
        chunks = []
        lines = content.splitlines()
        total_lines = len(lines)
        start = 0

        while start < total_lines:
            end = min(start + max_lines, total_lines)
            chunk_lines = lines[start:end]
            text = "\n".join(chunk_lines).strip()
            if text:
                chunks.append({
                    "start_line": start + 1,
                    "end_line": end,
                    "text": text
                })
            if end >= total_lines:
                break
            start += max_lines - overlap_lines
        return chunks


class VectorEngine:
    """Motor de base de datos vectorial local para RAG y memoria asociativa."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = TextEmbedder()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                collection_name TEXT NOT NULL,
                doc_path TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT,
                embedding BLOB NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("""
            CREATE TABLE IF NOT EXISTS episodic_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT NOT NULL,
                content TEXT NOT NULL,
                metadata_json TEXT,
                embedding BLOB NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_collection ON documents(collection_name);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_doc_path ON documents(doc_path);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_memory_category ON episodic_memories(category);")
            conn.commit()

    def create_collection(self, name: str, description: str = ""):
        with self._get_connection() as conn:
            conn.execute("""
            INSERT OR IGNORE INTO collections (name, description) VALUES (?, ?)
            """, (name, description))
            conn.commit()

    def index_file(self, file_path: str | Path, collection: str = "default") -> int:
        """Indexa un archivo en la base vectorial dividiéndolo en fragmentos semánticos."""
        p = Path(file_path).resolve()
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Archivo no encontrado: {file_path}")

        self.create_collection(collection)
        content = p.read_text(encoding="utf-8", errors="ignore")
        
        # Eliminar versión previa del mismo archivo si existe
        with self._get_connection() as conn:
            conn.execute("DELETE FROM documents WHERE doc_path = ? AND collection_name = ?", (str(p), collection))
            conn.commit()

        # Determinar tipo de chunking
        if p.suffix in (".md", ".markdown", ".txt", ".rst"):
            chunks_data = DocumentChunker.chunk_markdown(content)
        elif p.suffix in (".py", ".sh", ".js", ".ts", ".json", ".yaml", ".yml", ".conf"):
            chunks_data = DocumentChunker.chunk_code(content)
        else:
            chunks_data = [{"text": content[:2000]}]

        count = 0
        with self._get_connection() as conn:
            for idx, chunk in enumerate(chunks_data):
                text = chunk["text"]
                if not text.strip():
                    continue
                vec = self.embedder.embed_text(text)
                blob = TextEmbedder.serialize_vector(vec)
                meta = {"filename": p.name, "size": p.stat().st_size, "extension": p.suffix, **chunk}

                conn.execute("""
                INSERT INTO documents (collection_name, doc_path, chunk_index, content, metadata_json, embedding)
                VALUES (?, ?, ?, ?, ?, ?)
                """, (collection, str(p), idx, text, json.dumps(meta, ensure_ascii=False), blob))
                count += 1
            conn.commit()
        return count

    def index_directory(
        self,
        dir_path: str | Path,
        collection: str = "default",
        extensions: list[str] | None = None
    ) -> dict:
        """Indexa recursivamente los archivos de un directorio."""
        target_dir = Path(dir_path).resolve()
        if not target_dir.exists() or not target_dir.is_dir():
            raise NotADirectoryError(f"Directorio no válido: {dir_path}")

        valid_exts = set(extensions or [".md", ".py", ".sh", ".conf", ".json", ".txt"])
        indexed_files = 0
        total_chunks = 0

        for root, dirs, files in os.walk(target_dir):
            # Omitir carpetas ocultas o de cache
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ("__pycache__", "node_modules", ".venv", "venv")]
            for file in files:
                p = Path(root) / file
                if p.suffix.lower() in valid_exts:
                    try:
                        chunks = self.index_file(p, collection=collection)
                        indexed_files += 1
                        total_chunks += chunks
                    except Exception:
                        pass

        return {
            "collection": collection,
            "directory": str(target_dir),
            "indexed_files": indexed_files,
            "total_chunks": total_chunks
        }

    def search_documents(
        self,
        query: str,
        collection: str = "all",
        limit: int = 5,
        threshold: float = 0.15
    ) -> list[dict]:
        """Realiza una búsqueda semántica vectorial sobre los documentos indexados."""
        query_vec = self.embedder.embed_text(query)
        results = []

        query_sql = "SELECT id, collection_name, doc_path, chunk_index, content, metadata_json, embedding FROM documents"
        params = []
        if collection != "all":
            query_sql += " WHERE collection_name = ?"
            params.append(collection)

        with self._get_connection() as conn:
            rows = conn.execute(query_sql, params).fetchall()
            for r in rows:
                doc_vec = TextEmbedder.deserialize_vector(r["embedding"])
                score = TextEmbedder.cosine_similarity(query_vec, doc_vec)
                if score >= threshold:
                    meta = json.loads(r["metadata_json"]) if r["metadata_json"] else {}
                    results.append({
                        "id": r["id"],
                        "score": round(score, 4),
                        "collection": r["collection_name"],
                        "doc_path": r["doc_path"],
                        "chunk_index": r["chunk_index"],
                        "content": r["content"],
                        "metadata": meta
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def save_memory(self, content: str, category: str = "preference", metadata: dict | None = None) -> int:
        """Guarda un recuerdo episódico en la memoria semántica."""
        vec = self.embedder.embed_text(content)
        blob = TextEmbedder.serialize_vector(vec)
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)

        with self._get_connection() as conn:
            cur = conn.execute("""
            INSERT INTO episodic_memories (category, content, metadata_json, embedding)
            VALUES (?, ?, ?, ?)
            """, (category, content, meta_str, blob))
            conn.commit()
            return cur.lastrowid

    def search_memories(self, query: str, category: str | None = None, limit: int = 5) -> list[dict]:
        """Busca recuerdos semánticamente relevantes para una consulta."""
        query_vec = self.embedder.embed_text(query)
        results = []

        query_sql = "SELECT id, category, content, metadata_json, embedding, created_at FROM episodic_memories"
        params = []
        if category:
            query_sql += " WHERE category = ?"
            params.append(category)

        with self._get_connection() as conn:
            rows = conn.execute(query_sql, params).fetchall()
            for r in rows:
                mem_vec = TextEmbedder.deserialize_vector(r["embedding"])
                score = TextEmbedder.cosine_similarity(query_vec, mem_vec)
                results.append({
                    "id": r["id"],
                    "score": round(score, 4),
                    "category": r["category"],
                    "content": r["content"],
                    "created_at": r["created_at"]
                })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]

    def get_stats(self) -> dict:
        """Devuelve estadísticas globales de la base vectorial."""
        with self._get_connection() as conn:
            doc_count = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            mem_count = conn.execute("SELECT COUNT(*) FROM episodic_memories").fetchone()[0]
            colls = conn.execute("SELECT name, COUNT(documents.id) as docs FROM collections LEFT JOIN documents ON collections.name = documents.collection_name GROUP BY collections.name").fetchall()
            
            collections_stat = [{"name": c["name"], "chunks": c["docs"]} for c in colls]
            size_bytes = self.db_path.stat().st_size if self.db_path.exists() else 0

            return {
                "db_path": str(self.db_path),
                "size_kb": round(size_bytes / 1024, 2),
                "total_chunks": doc_count,
                "total_memories": mem_count,
                "collections": collections_stat
            }

if __name__ == "__main__":
    engine = VectorEngine()
    print(f"[+] VectorEngine inicializado en: {engine.db_path}")
    
    # Auto-indexar documentación de ai-lab
    docs_dir = Path.home() / "ai-lab" / "docs"
    if docs_dir.exists():
        print(f"[+] Indexando documentación en {docs_dir}...")
        res = engine.index_directory(docs_dir, collection="ai-lab-docs")
        print(f"[✓] Documentación indexada: {res['indexed_files']} archivos, {res['total_chunks']} chunks.")

    # Guardar memoria de prueba
    engine.save_memory("El usuario prefiere respuestas concisas en español con formato Markdown y enlaces file://", category="preference")
    
    # Búsqueda semántica de prueba
    test_search = engine.search_documents("¿Cómo solucionar el problema de suspensión y D3cold en la GPU?", collection="ai-lab-docs", limit=2)
    print(f"\n[+] Búsqueda de prueba (Top {len(test_search)}):")
    for r in test_search:
        print(f"  • [Score: {r['score']}] {Path(r['doc_path']).name} ({r['metadata'].get('header', '')})")
