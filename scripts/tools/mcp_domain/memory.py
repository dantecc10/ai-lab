"""Memory domain: persistent memory storage with SQLite."""

import os
import sqlite3

from mcp_common.paths import HOME
from mcp_common.logging import log_operation

MEMORY_DB = os.path.join(HOME, ".config/ai-memory.db")


def _get_db():
    conn = sqlite3.connect(MEMORY_DB)
    conn.row_factory = sqlite3.Row
    return conn


TOOLS = [
    {
        "name": "memory_save",
        "description": "Guarda información en la memoria persistente del asistente.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["note", "fact", "preference", "context", "task"], "description": "Categoría de la entrada."},
                "title": {"type": "string", "description": "Título o resumen corto."},
                "content": {"type": "string", "description": "Contenido completo de la entrada."},
                "tags": {"type": "string", "description": "Tags separados por comas."}
            },
            "required": ["category", "content"]
        }
    },
    {
        "name": "memory_search",
        "description": "Busca y recupera información de la memoria persistente por relevancia.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto o palabras clave a buscar."},
                "category": {"type": "string", "enum": ["note", "fact", "preference", "context", "task"], "description": "Filtrar por categoría."},
                "limit": {"type": "integer", "description": "Máximo de resultados. Default: 10."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "memory_get",
        "description": "Obtiene el contenido íntegro de una entrada de memoria por su ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "ID de la entrada."}
            },
            "required": ["id"]
        }
    },
    {
        "name": "memory_context",
        "description": "Obtiene las entradas más recientes de memoria para dar contexto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": ["note", "fact", "preference", "context", "task"]},
                "limit": {"type": "integer", "description": "Número de entradas. Default: 5."}
            },
            "required": []
        }
    },
    {
        "name": "memory_list",
        "description": "Lista el catálogo de entradas de memoria persistentes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Máximo de entradas. Default: 30."}
            },
            "required": []
        }
    },
    {
        "name": "memory_delete",
        "description": "Elimina una entrada de memoria por ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "description": "ID de la entrada a eliminar."}
            },
            "required": ["id"]
        }
    },
]


# ── Handlers ───────────────────────────────────────────────

def _memory_save(args):
    category = args["category"]
    content = args["content"]
    title = args.get("title")
    tags = args.get("tags", "")

    try:
        conn = _get_db()
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO memories (category, title, content, tags) VALUES (?, ?, ?, ?)",
            (category, title, content, tags)
        )
        conn.commit()
        entry_id = cursor.lastrowid
        conn.close()
        log_operation("memory_save", {"category": category, "title": title}, f"id={entry_id}")
        return f"💾 Guardado en memoria: [{category}] {title or content[:50]} (ID: {entry_id})"
    except Exception as e:
        return f"Error guardando en memoria: {e}"


def _memory_search(args):
    query = args["query"]
    category = args.get("category")
    limit = args.get("limit", 10)

    try:
        conn = _get_db()
        cursor = conn.cursor()
        if category:
            cursor.execute("SELECT * FROM memories WHERE category = ? ORDER BY created_at DESC", (category,))
        else:
            cursor.execute("SELECT * FROM memories ORDER BY created_at DESC")
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return f"No hay entradas en memoria (categoría: {category or 'todas'})."

        terms = [t.strip().lower() for t in query.split() if len(t.strip()) > 1]
        query_lower = query.lower().strip()
        scored = []

        for r in rows:
            title_text = (r['title'] or "").lower()
            content_text = (r['content'] or "").lower()
            tags_text = (r['tags'] or "").lower()
            combined = f"{title_text} {tags_text} {content_text}"

            score = 0
            if query_lower in combined:
                score += 100
            if query_lower in title_text:
                score += 50
            for term in terms:
                if term in title_text:
                    score += 35
                if term in tags_text:
                    score += 30
                if term in content_text:
                    score += 15
            if score > 0:
                scored.append((score, r))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:limit]

        if not top:
            return f"🔍 No se encontraron coincidencias para '{query}'. Usa memory_list para ver el catálogo."

        lines = [f"🧠 Memorias para '{query}' ({len(top)} resultados):\n"]
        for score, row in top:
            tags_str = f" [tags: {row['tags']}]" if row['tags'] else ""
            lines.append(f"📌 [ID: {row['id']}] [{row['category'].upper()}] {row['title'] or 'Sin título'}{tags_str}")
            lines.append(f"   {row['content']}")
            lines.append(f"   📅 Guardado: {row['created_at']}")
            lines.append("-" * 40)

        return "\n".join(lines)
    except Exception as e:
        return f"Error buscando en memoria: {e}"


def _memory_get(args):
    id = args["id"]
    try:
        conn = _get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE id = ?", (id,))
        row = cursor.fetchone()
        conn.close()

        if not row:
            return f"No se encontró memoria con ID {id}."

        tags_str = f" [tags: {row['tags']}]" if row['tags'] else ""
        return (
            f"📌 [ID: {row['id']}] [{row['category'].upper()}] {row['title'] or 'Sin título'}{tags_str}\n"
            f"   {row['content']}\n"
            f"   📅 Creado: {row['created_at']}"
        )
    except Exception as e:
        return f"Error recuperando memoria ID {id}: {e}"


def _memory_context(args):
    category = args.get("category")
    limit = args.get("limit", 5)

    try:
        conn = _get_db()
        cursor = conn.cursor()
        if category:
            cursor.execute("SELECT * FROM memories WHERE category = ? ORDER BY created_at DESC LIMIT ?", (category, limit))
        else:
            cursor.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No hay entradas en memoria."

        lines = ["📚 Contexto de memoria reciente:\n"]
        for row in rows:
            lines.append(f"📌 [{row['category'].upper()}] {row['title'] or 'Sin título'}")
            lines.append(f"   {row['content']}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        return f"Error obteniendo contexto: {e}"


def _memory_list(args):
    limit = args.get("limit", 30)

    try:
        conn = _get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories ORDER BY created_at DESC LIMIT ?", (limit,))
        rows = cursor.fetchall()
        conn.close()

        if not rows:
            return "No hay entradas en memoria."

        lines = [f"📋 Catálogo de memorias ({len(rows)} entradas):\n"]
        for row in rows:
            tags_str = f" [{row['tags']}]" if row['tags'] else ""
            preview = row['content'][:110].replace("\n", " ") + ("..." if len(row['content']) > 110 else "")
            lines.append(f"  • [ID: {row['id']}] [{row['category'].upper()}] {row['title'] or 'Sin título'}{tags_str}")
            lines.append(f"    ↪ {preview}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listando memoria: {e}"


def _memory_delete(args):
    id = args["id"]
    try:
        conn = _get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM memories WHERE id = ?", (id,))
        row = cursor.fetchone()
        if not row:
            conn.close()
            return f"Error: No se encontró entrada con ID {id}"

        cursor.execute("DELETE FROM memories WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        log_operation("memory_delete", {"id": id}, "deleted")
        return f"🗑️ Eliminada entrada [{id}]: {row['title'] or row['content'][:50]}"
    except Exception as e:
        return f"Error eliminando de memoria: {e}"


HANDLERS = {
    "memory_save": _memory_save,
    "memory_search": _memory_search,
    "memory_get": _memory_get,
    "memory_context": _memory_context,
    "memory_list": _memory_list,
    "memory_delete": _memory_delete,
}
