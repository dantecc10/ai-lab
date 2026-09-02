"""Vector search and memory tools"""

import os
from pathlib import Path


TOOLS = [
    {
        "name": "vector_search",
        "description": "Realiza búsqueda semántica vectorial (RAG) en los documentos, código y base de conocimiento indexada de AI Lab.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Consulta o pregunta en lenguaje natural."
                },
                "collection": {
                    "type": "string",
                    "description": "Colección a consultar (ej: 'ai-lab-docs', 'code', 'all') (default: 'all')."
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de fragmentos relevantes a retornar (default: 5)."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "vector_index_path",
        "description": "Indexa semánticamente un archivo o carpeta en la base de datos vectorial local para RAG.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta absoluta o relativa del archivo o carpeta a indexar."
                },
                "collection": {
                    "type": "string",
                    "description": "Nombre de la colección destino (ej: 'ai-lab-docs', 'project', 'notes') (default: 'docs')."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "vector_remember",
        "description": "Guarda un recuerdo episódico o preferencia en la memoria semántica vectorial de largo plazo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Texto del recuerdo, preferencia o hecho a almacenar."
                },
                "category": {
                    "type": "string",
                    "description": "Categoría del recuerdo (ej: 'preference', 'project', 'architecture', 'general') (default: 'preference')."
                }
            },
            "required": ["text"]
        }
    },
    {
        "name": "vector_stats",
        "description": "Consulta estadísticas de la base de datos vectorial local (colecciones, fragmentos indexados, memorias y tamaño).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
]

# ── Handlers ───────────────────────────────────────────────
def _vector_search_handler(query: str, collection: str = "all", limit: int = 5) -> str:
    """Búsqueda semántica en base vectorial local."""
    try:
        from scripts.tools.vector_engine import VectorEngine
        engine = VectorEngine()
        results = engine.search_documents(query, collection=collection, limit=limit)
        if not results:
            return f"ℹ️ No se encontraron fragmentos semánticamente relevantes para '{query}' en la colección '{collection}'."

        output = f"🔍 **Resultados de Búsqueda Semántica ({len(results)} fragmentos):**\n\n"
        for idx, r in enumerate(results, 1):
            score_pct = round(r["score"] * 100, 1)
            filename = Path(r["doc_path"]).name
            header = r.get("metadata", {}).get("header", "")
            hdr_str = f" > {header}" if header else ""
            output += f"**{idx}. [{score_pct}% Similitud] `{filename}`{hdr_str}** (Colección: `{r['collection']}`)\n"
            output += f"```markdown\n{r['content'][:350]}...\n```\n\n"
        return output.strip()
    except Exception as e:
        return f"Error en búsqueda semántica vectorial: {e}"



def _vector_index_path_handler(path: str, collection: str = "docs") -> str:
    """Indexa un archivo o carpeta en la base vectorial."""
    try:
        from scripts.tools.vector_engine import VectorEngine
        engine = VectorEngine()
        p = Path(path).expanduser().resolve()
        if not p.exists():
            return f"Error: La ruta '{path}' no existe."

        if p.is_file():
            chunks = engine.index_file(p, collection=collection)
            return f"✅ Archivo `{p.name}` indexado exitosamente en colección `{collection}` ({chunks} fragmentos semánticos)."
        else:
            res = engine.index_directory(p, collection=collection)
            return f"✅ Directorio `{p.name}` indexado en `{collection}`: {res['indexed_files']} archivos, {res['total_chunks']} fragmentos totales."
    except Exception as e:
        return f"Error al indexar ruta '{path}': {e}"



def _vector_remember_handler(text: str, category: str = "preference") -> str:
    """Guarda un recuerdo en la memoria episódica vectorial."""
    try:
        from scripts.tools.vector_engine import VectorEngine
        engine = VectorEngine()
        mem_id = engine.save_memory(text, category=category)
        return f"🧠 Recuerdo #{mem_id} guardado exitosamente en la memoria vectorial (Categoría: `{category}`)."
    except Exception as e:
        return f"Error al guardar memoria semántica: {e}"



def _vector_stats_handler() -> str:
    """Devuelve estadísticas de la base vectorial."""
    try:
        from scripts.tools.vector_engine import VectorEngine
        engine = VectorEngine()
        stats = engine.get_stats()
        output = "📊 **Estadísticas de la Base Vectorial Local (RAG):**\n\n"
        output += f"• **Ubicación**: `{stats['db_path']}`\n"
        output += f"• **Tamaño en disco**: {stats['size_kb']} KB\n"
        output += f"• **Total fragmentos de documentos**: {stats['total_chunks']}\n"
        output += f"• **Total recuerdos episódicos**: {stats['total_memories']}\n\n"
        output += "📁 **Colecciones:**\n"
        for c in stats["collections"]:
            output += f"  - `{c['name']}`: {c['chunks']} chunks\n"
        return output
    except Exception as e:
        return f"Error al consultar estadísticas vectoriales: {e}"


# ── Headless Browser & Identity Sync Tools (Brave CDP) ──────

HANDLERS = {
    "vector_search": _vector_search_handler,
    "vector_index_path": _vector_index_path_handler,
    "vector_remember": _vector_remember_handler,
    "vector_stats": _vector_stats_handler,
}
