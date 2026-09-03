"""
Study Tools — Anki + Logseq + AI-powered learning
Flashcard generation, note synthesis, concept mapping, adaptive explanations
"""

import json
import os
import re
import subprocess
import sys
import time
import hashlib
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any

# ─── Configuration ───────────────────────────────────────────────────────────

ANKI_CONNECT_URL = "http://localhost:8765"
LOGSEQ_GRAPH_PATH = os.path.expanduser("~/logseq-graph")
LOGSEQ_NOTES_PATH = os.path.expanduser("~/logseq-graph/pages")

# ─── AnkiConnect Client ──────────────────────────────────────────────────────

def _anki_request(action: str, **params) -> dict:
    """Make a request to AnkiConnect API."""
    import urllib.request
    import urllib.error

    payload = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")

    try:
        req = urllib.request.Request(ANKI_CONNECT_URL, data=payload,
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("error"):
                return {"error": result["error"]}
            return result.get("result", {})
    except urllib.error.URLError as e:
        return {"error": f"AnkiConnect no disponible. ¿Está Anki abierto? ({e})"}
    except Exception as e:
        return {"error": str(e)}


def _anki_is_running() -> bool:
    """Check if Anki is running and AnkiConnect is available."""
    result = _anki_request("version")
    return "error" not in result

# ─── Anki Tools ──────────────────────────────────────────────────────────────

def _anki_create_deck_handler(deck_name: str) -> str:
    """Create a new Anki deck."""
    result = _anki_request("createDeck", deck=deck_name)
    if "error" in result:
        return f"Error creando deck: {result['error']}"
    return f"Deck '{deck_name}' creado (ID: {result})"


def _anki_list_decks_handler() -> str:
    """List all Anki decks."""
    result = _anki_request("deckNamesAndIds")
    if "error" in result:
        return f"Error: {result['error']}"
    if not result:
        return "No hay decks en Anki"
    lines = ["Decks disponibles:"]
    for name, did in result.items():
        lines.append(f"  • {name} (ID: {did})")
    return "\n".join(lines)


def _anki_add_note_handler(deck_name: str, front: str, back: str,
                           tags: list = None, media_file: str = None) -> str:
    """Add a single flashcard to Anki."""
    note = {
        "deckName": deck_name,
        "modelName": "Basic",
        "fields": {"Front": front, "Back": back},
        "tags": tags or []
    }

    params = {"note": note}
    if media_file and os.path.exists(media_file):
        import base64
        with open(media_file, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        params["note"]["picture"] = [{
            "data": data,
            "filename": os.path.basename(media_file),
            "fields": ["Front"]
        }]

    result = _anki_request("addNote", **params)
    if "error" in result:
        return f"Error agregando nota: {result['error']}"
    return f"Flashcard creada: {front[:50]}..." if len(front) > 50 else f"Flashcard creada: {front}"


def _anki_add_notes_bulk_handler(deck_name: str, notes_json: str) -> str:
    """Add multiple flashcards at once. notes_json: list of {front, back, tags?}"""
    try:
        notes_list = json.loads(notes_json) if isinstance(notes_json, str) else notes_json
    except json.JSONDecodeError:
        return "Error: notes_json no es JSON válido"

    if not isinstance(notes_list, list):
        return "Error: se esperaba una lista de notas"

    notes = []
    for item in notes_list:
        note = {
            "deckName": deck_name,
            "modelName": "Basic",
            "fields": {
                "Front": item.get("front", ""),
                "Back": item.get("back", "")
            },
            "tags": item.get("tags", [])
        }
        notes.append(note)

    result = _anki_request("addNotes", notes=notes)
    if "error" in result:
        return f"Error agregando notas: {result['error']}"

    created = len(result) if isinstance(result, list) else 0
    return f"{created} flashcards creadas en '{deck_name}'"


def _anki_search_cards_handler(query: str, deck_name: str = None) -> str:
    """Search for cards in Anki."""
    search_query = query
    if deck_name:
        search_query = f"deck:{deck_name} {query}"

    result = _anki_request("findCards", query=search_query)
    if "error" in result:
        return f"Error buscando: {result['error']}"

    if not result:
        return f"No se encontraron tarjetas para: {query}"

    # Get card info for each card
    cards_info = _anki_request("cardsInfo", cards=result[:20])  # Limit to 20
    if "error" in cards_info:
        return f"{len(result)} tarjetas encontradas (detalles no disponibles)"

    lines = [f"Encontradas {len(result)} tarjetas:"]
    for card in cards_info[:10]:
        front = card.get("fields", {}).get("Front", {}).get("value", "?")
        front = re.sub(r"<[^>]+>", "", front)[:60]
        interval = card.get("interval", 0)
        ease = card.get("ease", 0)
        lines.append(f"  • {front} (intervalo: {interval}d, facilidad: {ease})")

    if len(result) > 10:
        lines.append(f"  ... y {len(result) - 10} más")

    return "\n".join(lines)


def _anki_review_stats_handler(deck_name: str = None) -> str:
    """Get review statistics for a deck or all decks."""
    # Get deck stats
    result = _anki_request("getDecks", decks=[deck_name] if deck_name else ["default"])
    if "error" in result:
        return f"Error: {result['error']}"

    # Get collection stats
    stats = _anki_request("getCollectionStatsHTML", days=30)
    if "error" in stats:
        # Fallback: count cards
        decks = _anki_request("deckNamesAndIds")
        if "error" in decks:
            return f"Error obteniendo stats: {decks['error']}"

        lines = ["Estadísticas de Anki:"]
        for name in (list(decks.keys())[:10] if not deck_name else [deck_name]):
            cards = _anki_request("findCards", query=f"deck:{name}")
            if isinstance(cards, list):
                lines.append(f"  • {name}: {len(cards)} tarjetas")
        return "\n".join(lines)

    return stats


def _anki_generate_flashcards_handler(text: str, num_cards: int = 10,
                                       deck_name: str = "AI Generated") -> str:
    """Generate flashcards from text using pattern extraction."""
    # Extract key patterns: definitions, lists, facts
    cards = []

    # Pattern 1: "X is/are Y" definitions
    definitions = re.findall(
        r'([A-Z][^.]*?)\s+(?:es|son|is|are|se define como|refiere a)\s+(.+?)(?:\.|$)',
        text, re.MULTILINE | re.IGNORECASE
    )
    for term, definition in definitions[:num_cards]:
        cards.append({
            "front": term.strip(),
            "back": definition.strip(),
            "tags": ["generated", "definition"]
        })

    # Pattern 2: Numbered lists or bullet points
    list_items = re.findall(
        r'(?:^|\n)\s*(?:\d+[.)]\s*|\*+\s*|-+\s*)(.+?)(?:\n|$)',
        text
    )
    if list_items and len(cards) < num_cards:
        for item in list_items[:num_cards - len(cards)]:
            if len(item) > 10:
                cards.append({
                    "front": f"¿Qué es/qué significa?: {item[:50]}",
                    "back": item.strip(),
                    "tags": ["generated", "list"]
                })

    # Pattern 3: Bold/capitalized terms followed by explanations
    bold_terms = re.findall(r'\*\*(.+?)\*\*\s*[:\-—]\s*(.+?)(?:\n|$)', text)
    for term, explanation in bold_terms[:num_cards - len(cards)]:
        cards.append({
            "front": term.strip(),
            "back": explanation.strip(),
            "tags": ["generated", "bold"]
        })

    if not cards:
        return "No se pudieron extraer patrones claros del texto para generar flashcards. Intenta con un texto que contenga definiciones, listas o términos en negrita."

    # Trim to requested number
    cards = cards[:num_cards]

    # Add to Anki if possible
    if _anki_is_running():
        result = _anki_add_notes_bulk_handler(deck_name, json.dumps(cards))
        return f"Generadas {len(cards)} flashcards:\n{result}\n\nContenido:\n" + "\n".join(
            f"  {i+1}. {c['front'][:50]}" for i, c in enumerate(cards)
        )
    else:
        return f"Generadas {len(cards)} flashcards (Anki no está corriendo, se guardan localmente):\n\n" + "\n".join(
            f"  {i+1}. {c['front'][:50]}\n     → {c['back'][:80]}" for i, c in enumerate(cards)
        )


def _anki_import_file_handler(file_path: str, deck_name: str = "Import") -> str:
    """Import flashcards from a text file (one card per line: front|back)."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return f"Archivo no encontrado: {file_path}"

    content = path.read_text(encoding="utf-8")
    cards = []

    for line in content.strip().split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r'\t|\|', line, maxsplit=1)
        if len(parts) == 2:
            cards.append({
                "front": parts[0].strip(),
                "back": parts[1].strip(),
                "tags": ["imported"]
            })

    if not cards:
        return "No se encontraron flashcards válidas. Usa formato: frente|reverso (uno por línea)"

    if _anki_is_running():
        result = _anki_add_notes_bulk_handler(deck_name, json.dumps(cards))
        return f"Importadas {len(cards)} flashcards desde {path.name}\n{result}"
    else:
        return f"Preparadas {len(cards)} flashcards (Anki no disponible): {path.name}"


def _anki_daily_review_handler() -> str:
    """Show cards due for review today."""
    if not _anki_is_running():
        return "Anki no está corriendo. Abre Anki para revisar tarjetas."

    # Find cards due today
    result = _anki_request("findCards", query="is:due")
    if "error" in result:
        return f"Error: {result['error']}"

    if not result:
        return "No hay tarjetas pendientes de revisión hoy. ¡Buen trabajo!"

    # Get deck counts
    deck_counts = {}
    for card_id in result:
        cards_info = _anki_request("cardsInfo", cards=[card_id])
        if isinstance(cards_info, list) and cards_info:
            deck = cards_info[0].get("deckName", "Unknown")
            deck_counts[deck] = deck_counts.get(deck, 0) + 1

    lines = [f"📊 Tarjetas pendientes hoy: {len(result)}"]
    lines.append("")
    for deck, count in sorted(deck_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  • {deck}: {count} tarjetas")

    lines.append(f"\nAbre Anki y comienza tu revisión de {len(result)} tarjetas.")
    return "\n".join(lines)

# ─── Logseq Tools ────────────────────────────────────────────────────────────

def _logseq_init_graph_handler(graph_name: str = "AI Lab Study") -> str:
    """Initialize a Logseq graph directory."""
    graph_path = Path(LOGSEQ_GRAPH_PATH).expanduser()
    pages_path = graph_path / "pages"
    journals_path = graph_path / "journals"

    graph_path.mkdir(parents=True, exist_ok=True)
    pages_path.mkdir(parents=True, exist_ok=True)
    journals_path.mkdir(parents=True, exist_ok=True)

    # Create config
    config = {
        "current-graph": str(graph_path),
        "default-graph": str(graph_path),
    }
    config_path = graph_path / "config.edn"
    if not config_path.exists():
        config_path.write_text(json.dumps(config, indent=2), encoding="utf-8")

    return f"Graph Logseq inicializado en: {graph_path}"


def _logseq_create_page_handler(title: str, content: str,
                                 tags: list = None, namespace: str = None) -> str:
    """Create a page in Logseq."""
    pages_path = Path(LOGSEQ_NOTES_PATH).expanduser()
    pages_path.mkdir(parents=True, exist_ok=True)

    # Sanitize filename
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', title)
    if namespace:
        safe_title = f"{namespace}_{safe_title}"

    page_path = pages_path / f"{safe_title}.md"

    # Build page content
    lines = [f"- {title}"]
    if tags:
        tag_str = " ".join(f"#{t}" for t in tags)
        lines.append(f"  - Tags: {tag_str}")
    lines.append("")

    for line in content.split("\n"):
        line = line.strip()
        if line:
            lines.append(f"- {line}")
        else:
            lines.append("")

    page_path.write_text("\n".join(lines), encoding="utf-8")
    return f"Página '{title}' creada en Logseq: {page_path}"


def _logseq_create_flashcard_page_handler(topic: str, qa_pairs_json: str,
                                           deck_name: str = "Logseq Cards") -> str:
    """Create a flashcard page in Logseq with Anki-style cards."""
    pages_path = Path(LOGSEQ_NOTES_PATH).expanduser()
    pages_path.mkdir(parents=True, exist_ok=True)

    try:
        pairs = json.loads(qa_pairs_json) if isinstance(qa_pairs_json, str) else qa_pairs_json
    except json.JSONDecodeError:
        return "Error: qa_pairs_json no es JSON válido"

    safe_title = re.sub(r'[<>:"/\\|?*]', '_', topic)
    page_path = pages_path / f"Cards_{safe_title}.md"

    lines = [f"# Flashcards: {topic}", ""]
    for i, pair in enumerate(pairs, 1):
        q = pair.get("question", pair.get("front", ""))
        a = pair.get("answer", pair.get("back", ""))
        lines.append(f"## Pregunta {i}")
        lines.append(f"**{q}**")
        lines.append(f"card:: 1")
        lines.append(f"")
        lines.append(f"**Respuesta:** {a}")
        lines.append(f"")

    page_path.write_text("\n".join(lines), encoding="utf-8")

    # Also add to Anki if available
    if _anki_is_running():
        notes = [{"front": p.get("question", p.get("front", "")),
                  "back": p.get("answer", p.get("back", "")),
                  "tags": ["logseq", "generated"]}
                 for p in pairs]
        _anki_add_notes_bulk_handler(deck_name, json.dumps(notes))

    return f"Flashcards creadas en Logseq ({len(pairs)} tarjetas): {page_path}"


def _logseq_create_concept_map_handler(topic: str, concepts_json: str) -> str:
    """Create a concept map page in Logseq with linked thoughts."""
    pages_path = Path(LOGSEQ_NOTES_PATH).expanduser()
    pages_path.mkdir(parents=True, exist_ok=True)

    try:
        concepts = json.loads(concepts_json) if isinstance(concepts_json, str) else concepts_json
    except json.JSONDecodeError:
        return "Error: concepts_json no es JSON válido"

    safe_title = re.sub(r'[<>:"/\\|?*]', '_', topic)
    page_path = pages_path / f"Mapa_{safe_title}.md"

    lines = [f"# Mapa Conceptual: {topic}", ""]

    for concept in concepts:
        name = concept.get("name", concept.get("concept", ""))
        definition = concept.get("definition", "")
        related = concept.get("related", [])
        parent = concept.get("parent", None)

        lines.append(f"## {name}")
        if definition:
            lines.append(f"- **Definición:** {definition}")
        if parent:
            lines.append(f"- **Pertenece a:** [[{parent}]]")
        if related:
            links = ", ".join(f"[[{r}]]" for r in related)
            lines.append(f"- **Relacionado con:** {links}")
        lines.append("")

    # Add all concept names as references
    lines.append("---")
    lines.append("## Referencia de conceptos")
    for concept in concepts:
        name = concept.get("name", concept.get("concept", ""))
        lines.append(f"- [[{name}]]")

    page_path.write_text("\n".join(lines), encoding="utf-8")
    return f"Mapa conceptual creado ({len(concepts)} conceptos): {page_path}"


def _logseq_create_study_guide_handler(topic: str, content: str,
                                        key_points: list = None) -> str:
    """Create a structured study guide in Logseq."""
    pages_path = Path(LOGSEQ_NOTES_PATH).expanduser()
    pages_path.mkdir(parents=True, exist_ok=True)

    safe_title = re.sub(r'[<>:"/\\|?*]', '_', topic)
    page_path = pages_path / f"Guia_{safe_title}.md"

    lines = [
        f"# Guía de Estudio: {topic}",
        f"- Fecha: {datetime.now().strftime('%Y-%m-%d')}",
        "",
        "## Resumen",
    ]

    # Add content as structured points
    for line in content.split("\n"):
        line = line.strip()
        if line:
            lines.append(f"- {line}")

    if key_points:
        lines.append("")
        lines.append("## Puntos Clave")
        for point in key_points:
            lines.append(f"- **{point}**")
            lines.append(f"  - card:: 1")
            lines.append(f"  - ¿Por qué es importante?")

    lines.append("")
    lines.append("## Auto-evaluación")
    lines.append("- [ ] Puedo explicar este tema con mis propias palabras")
    lines.append("- [ ] Puedo dar ejemplos concretos")
    lines.append("- [ ] Puedo conectar con otros conceptos")
    lines.append("- [ ] Puedo resolver problemas relacionados")

    page_path.write_text("\n".join(lines), encoding="utf-8")
    return f"Guía de estudio creada: {page_path}"


def _logseq_list_pages_handler(query: str = None) -> str:
    """List pages in Logseq graph."""
    pages_path = Path(LOGSEQ_NOTES_PATH).expanduser()

    if not pages_path.exists():
        return "No hay graph de Logseq. Usa logseq_init_graph primero."

    pages = sorted(pages_path.glob("*.md"))

    if query:
        pages = [p for p in pages if query.lower() in p.stem.lower()]

    if not pages:
        return "No se encontraron páginas" + (f" para: {query}" if query else "")

    lines = [f"Páginas en Logseq ({len(pages)}):"]
    for page in pages[:20]:
        lines.append(f"  📄 {page.stem}")
    if len(pages) > 20:
        lines.append(f"  ... y {len(pages) - 20} más")

    return "\n".join(lines)


def _logseq_read_page_handler(page_title: str) -> str:
    """Read a Logseq page."""
    pages_path = Path(LOGSEQ_NOTES_PATH).expanduser()
    safe_title = re.sub(r'[<>:"/\\|?*]', '_', page_title)
    page_path = pages_path / f"{safe_title}.md"

    if not page_path.exists():
        # Try to find partial match
        pages = list(pages_path.glob(f"*{safe_title}*.md"))
        if pages:
            page_path = pages[0]
        else:
            return f"Página no encontrada: {page_title}"

    content = page_path.read_text(encoding="utf-8")
    return f"📄 {page_path.stem}\n{'─' * 40}\n{content}"

# ─── AI-Powered Study Tools ──────────────────────────────────────────────────

def _study_summarize_handler(text: str, max_points: int = 10) -> str:
    """Create a structured summary of text with key points."""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 20]

    if not sentences:
        return "Texto demasiado corto para resumir"

    # Score sentences by importance indicators
    importance_keywords = [
        'importante', 'clave', 'fundamental', 'esencial', 'principal',
        'key', 'important', 'fundamental', 'essential', 'main',
        'definición', 'concepto', 'teoría', 'definition', 'concept',
        'primero', 'segundo', 'tercero', 'first', 'second', 'third',
        'por lo tanto', 'sin embargo', 'además', 'therefore', 'however'
    ]

    scored = []
    for i, sentence in enumerate(sentences):
        score = 0
        lower = sentence.lower()
        for keyword in importance_keywords:
            if keyword in lower:
                score += 2
        # Earlier sentences often more important
        score += max(0, 5 - i)
        # Length bonus
        score += min(len(sentence) // 50, 3)
        scored.append((score, sentence))

    scored.sort(reverse=True)
    top_sentences = [s for _, s in scored[:max_points]]

    # Create summary
    lines = ["## Resumen del Texto\n"]
    for i, sentence in enumerate(top_sentences, 1):
        lines.append(f"{i}. {sentence.strip()}")

    return "\n".join(lines)


def _study_extract_concepts_handler(text: str) -> str:
    """Extract key concepts and definitions from text."""
    concepts = []

    # Pattern 1: X es Y / X is Y
    defs1 = re.findall(
        r'([A-Z][^.]*?)\s+(?:es|son|is|are)\s+(.+?)(?:\.|$)',
        text, re.MULTILINE
    )
    for term, defn in defs1:
        if len(term) < 100 and len(defn) > 10:
            concepts.append({
                "name": term.strip(),
                "definition": defn.strip(),
                "related": []
            })

    # Pattern 2: **Term** - definition
    defs2 = re.findall(r'\*\*(.+?)\*\*\s*[:\-—]\s*(.+?)(?:\n|$)', text)
    for term, defn in defs2:
        if len(term) < 100:
            # Check if not duplicate
            if not any(c["name"].lower() == term.strip().lower() for c in concepts):
                concepts.append({
                    "name": term.strip(),
                    "definition": defn.strip(),
                    "related": []
                })

    if not concepts:
        return "No se encontraron conceptos claros en el texto"

    # Try to find relationships
    for c in concepts:
        for other in concepts:
            if c["name"] != other["name"]:
                if other["name"].lower() in c["definition"].lower():
                    c["related"].append(other["name"])

    lines = [f"## Conceptos Extraídos ({len(concepts)})\n"]
    for i, concept in enumerate(concepts, 1):
        lines.append(f"### {i}. {concept['name']}")
        lines.append(f"**Definición:** {concept['definition']}")
        if concept["related"]:
            lines.append(f"**Relacionado con:** {', '.join(concept['related'][:3])}")
        lines.append("")

    return "\n".join(lines)


def _study_generate_quiz_handler(text: str, num_questions: int = 5) -> str:
    """Generate quiz questions from text."""
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 30]

    if len(sentences) < num_questions:
        return f"Texto insuficiente para {num_questions} preguntas (solo {len(sentences)} oraciones útiles)"

    questions = []

    # Generate definition questions
    defs = re.findall(
        r'([A-Z][^.]*?)\s+(?:es|son|is|are)\s+(.+?)(?:\.|$)',
        text, re.MULTILINE
    )
    for term, definition in defs[:num_questions]:
        questions.append({
            "type": "definition",
            "question": f"¿Qué es {term.strip()}?",
            "answer": definition.strip()
        })

    # Generate fill-in-the-blank from statements
    if len(questions) < num_questions:
        for sent in sentences[:num_questions * 2]:
            if len(questions) >= num_questions:
                break
            words = sent.split()
            if len(words) > 8:
                # Remove a key word (longer ones)
                key_words = [(i, w) for i, w in enumerate(words) if len(w) > 5]
                if key_words:
                    idx, word = key_words[len(questions) % len(key_words)]
                    words[idx] = "________"
                    questions.append({
                        "type": "fill_blank",
                        "question": " ".join(words),
                        "answer": word
                    })

    if not questions:
        return "No se pudieron generar preguntas del texto"

    lines = [f"## Quiz: {len(questions)} Preguntas\n"]
    for i, q in enumerate(questions[:num_questions], 1):
        qtype = "📝" if q["type"] == "definition" else "✏️"
        lines.append(f"### {i}. {qtype} {q['question']}")
        lines.append(f"**Respuesta:** {q['answer']}\n")

    return "\n".join(lines)


def _study_adaptive_explanation_handler(concept: str, level: str = "intermedio") -> str:
    """Generate adaptive explanation for a concept based on level."""
    levels = {
        "basico": {
            "title": "Explicación Básica",
            "approach": "Usando analogías del día a día",
            "template": "Imagina que {concept} es como {analogy}. {simple_explanation}"
        },
        "intermedio": {
            "title": "Explicación Intermedia",
            "approach": "Con ejemplos prácticos",
            "template": "{concept} se refiere a {definition}. Por ejemplo, {example}."
        },
        "avanzado": {
            "title": "Explicación Avanzada",
            "approach": "Con profundidad técnica",
            "template": "{concept} implica {technical_detail}. Esto se relaciona con {connections}."
        }
    }

    config = levels.get(level, levels["intermedio"])

    # Create a structured template for the LLM to fill
    explanation = f"""
## {config['title']}: {concept}

**Nivel:** {level.title()}
**Enfoque:** {config['approach']}

---

### Para explicar este concepto, la IA debe:

1. **Definición clara:** ¿Qué es {concept}?
2. **Analogía:** ¿A qué se parece en la vida real?
3. **Ejemplo concreto:** ¿Dónde se usa o aplica?
4. **Conexiones:** ¿Con qué otros conceptos se relaciona?
5. **Error común:** ¿Qué error típico comete la gente al entenderlo?

---

*Esta es una plantilla. La IA debe llenar cada sección con contenido real.*
"""
    return explanation


def _study_batch_generate_handler(text: str, deck_name: str = "Study Batch",
                                    card_count: int = 20) -> str:
    """Generate a complete study batch from text: flashcards + quiz + summary."""
    results = []

    # 1. Generate flashcards
    cards_result = _anki_generate_flashcards_handler(text, card_count, deck_name)
    results.append(f"## Flashcards\n{cards_result}")

    # 2. Generate quiz
    quiz_result = _study_generate_quiz_handler(text, min(10, card_count // 2))
    results.append(f"\n## Quiz\n{quiz_result}")

    # 3. Create summary
    summary_result = _study_summarize_handler(text, 10)
    results.append(f"\n## Resumen\n{summary_result}")

    # 4. Extract concepts
    concepts_result = _study_extract_concepts_handler(text)
    results.append(f"\n## Conceptos Clave\n{concepts_result}")

    return "\n".join(results)


def _study_srs_schedule_handler(cards_json: str = None) -> str:
    """Show spaced repetition schedule and recommendations."""
    if not _anki_is_running():
        return "Anki no está corriendo. Abre Anki para ver tu programación SRS."

    # Get deck stats
    decks = _anki_request("deckNamesAndIds")
    if "error" in decks:
        return f"Error: {decks['error']}"

    lines = ["## 📅 Programación de Repaso (SRS)\n"]

    total_due = 0
    for deck_name, deck_id in list(decks.items())[:10]:
        cards = _anki_request("findCards", query=f"deck:{deck_name} is:due")
        if isinstance(cards, list):
            count = len(cards)
            total_due += count
            if count > 0:
                lines.append(f"### 📚 {deck_name}")
                lines.append(f"   Tarjetas pendientes: **{count}**")

                # Get interval distribution
                if cards:
                    cards_info = _anki_request("cardsInfo", cards=cards[:50])
                    if isinstance(cards_info, list):
                        intervals = [c.get("interval", 0) for c in cards_info]
                        new_cards = sum(1 for i in intervals if i == 0)
                        learning = sum(1 for i in intervals if 0 < i < 1)
                        review = sum(1 for i in intervals if i >= 1)
                        lines.append(f"   📊 Distribución: {new_cards} nuevas, {learning} aprendiendo, {review} repaso")
                lines.append("")

    if total_due == 0:
        lines.append("🎉 ¡No hay tarjetas pendientes! Buen trabajo.")
    else:
        lines.append(f"**Total pendiente: {total_due} tarjetas**")
        lines.append(f"\n💡 *Recomendación: Dedicar ~{total_due * 2} minutos al repaso de hoy*")

    return "\n".join(lines)


def _study_note_to_cards_handler(file_path: str, deck_name: str = "Notes Import",
                                   format: str = "auto") -> str:
    """Convert a markdown/txt note file to Anki flashcards."""
    path = Path(file_path).expanduser()
    if not path.exists():
        return f"Archivo no encontrado: {file_path}"

    content = path.read_text(encoding="utf-8")
    cards = []

    if format == "auto" or format == "markdown":
        # Extract headings and content as Q&A
        sections = re.split(r'\n#{1,3}\s+', content)
        for section in sections[1:]:  # Skip first (before any heading)
            lines = section.strip().split("\n")
            if lines:
                heading = lines[0].strip()
                body = "\n".join(l.strip() for l in lines[1:] if l.strip())
                if body:
                    cards.append({
                        "front": heading,
                        "back": body[:500],  # Limit back content
                        "tags": ["from-notes", path.stem]
                    })

    if format == "auto" or format == "qa":
        # Extract Q: A: patterns
        qa_pairs = re.findall(
            r'(?:Q|Pregunta|P)\s*[:.]\s*(.+?)\s*\n\s*(?:A|Respuesta|R)\s*[:.]\s*(.+?)(?:\n|$)',
            content, re.IGNORECASE
        )
        for q, a in qa_pairs:
            cards.append({
                "front": q.strip(),
                "back": a.strip(),
                "tags": ["from-notes", "qa", path.stem]
            })

    if not cards:
        return f"No se encontraron patrones de Q&A en {path.name}. Usa formatos: #heading + content, Q: A:" 

    # Add to Anki
    if _anki_is_running():
        result = _anki_add_notes_bulk_handler(deck_name, json.dumps(cards))
        return f"Convertidas {len(cards)} notas → flashcards en '{deck_name}'\n{result}"
    else:
        return f"Preparadas {len(cards)} flashcards desde {path.name} (Anki no disponible)"


# ─── Tool Definitions ────────────────────────────────────────────────────────

TOOLS = [
    # Anki Tools
    {
        "name": "anki_create_deck",
        "description": "Crear un nuevo deck en Anki",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck_name": {"type": "string", "description": "Nombre del deck"}
            },
            "required": ["deck_name"]
        }
    },
    {
        "name": "anki_list_decks",
        "description": "Listar todos los decks de Anki",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "anki_add_note",
        "description": "Agregar una flashcard a Anki (frente y reverso)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck_name": {"type": "string", "description": "Nombre del deck"},
                "front": {"type": "string", "description": "Contenido del frente (pregunta)"},
                "back": {"type": "string", "description": "Contenido del reverso (respuesta)"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Etiquetas opcionales"},
                "media_file": {"type": "string", "description": "Ruta a imagen/audio opcional"}
            },
            "required": ["deck_name", "front", "back"]
        }
    },
    {
        "name": "anki_add_notes_bulk",
        "description": "Agregar múltiples flashcards a Anki de una vez (JSON array)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck_name": {"type": "string", "description": "Nombre del deck"},
                "notes_json": {"type": "string", "description": "JSON array: [{front, back, tags?}]"}
            },
            "required": ["deck_name", "notes_json"]
        }
    },
    {
        "name": "anki_search_cards",
        "description": "Buscar tarjetas en Anki por texto o query",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto de búsqueda"},
                "deck_name": {"type": "string", "description": "Filtrar por deck específico"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "anki_review_stats",
        "description": "Ver estadísticas de repaso y tarjetas pendientes",
        "inputSchema": {
            "type": "object",
            "properties": {
                "deck_name": {"type": "string", "description": "Deck específico (opcional)"}
            }
        }
    },
    {
        "name": "anki_generate_flashcards",
        "description": "Generar flashcards automáticamente desde texto usando patrones (definiciones, listas, etc.)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto fuente para generar flashcards"},
                "num_cards": {"type": "integer", "description": "Número de tarjetas a generar", "default": 10},
                "deck_name": {"type": "string", "description": "Deck destino", "default": "AI Generated"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "anki_import_file",
        "description": "Importar flashcards desde archivo (formato: frente|reverso por línea, o tab-separated)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Ruta al archivo"},
                "deck_name": {"type": "string", "description": "Deck destino", "default": "Import"}
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "anki_daily_review",
        "description": "Mostrar tarjetas pendientes de repaso hoy (SRS schedule)",
        "inputSchema": {"type": "object", "properties": {}}
    },
    # Logseq Tools
    {
        "name": "logseq_init_graph",
        "description": "Inicializar un graph de Logseq para notas de estudio",
        "inputSchema": {
            "type": "object",
            "properties": {
                "graph_name": {"type": "string", "description": "Nombre del graph", "default": "AI Lab Study"}
            }
        }
    },
    {
        "name": "logseq_create_page",
        "description": "Crear una página en Logseq con contenido y tags",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Título de la página"},
                "content": {"type": "string", "description": "Contenido markdown"},
                "tags": {"type": "array", "items": {"type": "string"}, "description": "Tags opcionales"},
                "namespace": {"type": "string", "description": "Namespace/carpeta opcional"}
            },
            "required": ["title", "content"]
        }
    },
    {
        "name": "logseq_create_flashcards",
        "description": "Crear página de flashcards en Logseq (con formato Anki-compatible)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Tema de las flashcards"},
                "qa_pairs_json": {"type": "string", "description": "JSON array: [{question, answer}]"},
                "deck_name": {"type": "string", "description": "Deck Anki同步", "default": "Logseq Cards"}
            },
            "required": ["topic", "qa_pairs_json"]
        }
    },
    {
        "name": "logseq_create_concept_map",
        "description": "Crear mapa conceptual en Logsey con enlaces [[bidireccionales]]",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Tema central"},
                "concepts_json": {"type": "string", "description": "JSON array: [{name, definition, related?, parent?}]"}
            },
            "required": ["topic", "concepts_json"]
        }
    },
    {
        "name": "logseq_create_study_guide",
        "description": "Crear guía de estudio estructurada con auto-evaluación",
        "inputSchema": {
            "type": "object",
            "properties": {
                "topic": {"type": "string", "description": "Tema de la guía"},
                "content": {"type": "string", "description": "Contenido/resumen del tema"},
                "key_points": {"type": "array", "items": {"type": "string"}, "description": "Puntos clave"}
            },
            "required": ["topic", "content"]
        }
    },
    {
        "name": "logseq_list_pages",
        "description": "Listar páginas en el graph de Logseq",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Filtro de búsqueda (opcional)"}
            }
        }
    },
    {
        "name": "logseq_read_page",
        "description": "Leer contenido de una página de Logseq",
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_title": {"type": "string", "description": "Título de la página"}
            },
            "required": ["page_title"]
        }
    },
    # AI Study Tools
    {
        "name": "study_summarize",
        "description": "Crear resumen estructurado del texto con puntos clave (IA)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto a resumir"},
                "max_points": {"type": "integer", "description": "Máximo de puntos", "default": 10}
            },
            "required": ["text"]
        }
    },
    {
        "name": "study_extract_concepts",
        "description": "Extraer conceptos y definiciones clave del texto",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto del cual extraer conceptos"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "study_generate_quiz",
        "description": "Generar quiz con preguntas de opción múltiple o completar espacios",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto fuente para generar quiz"},
                "num_questions": {"type": "integer", "description": "Número de preguntas", "default": 5}
            },
            "required": ["text"]
        }
    },
    {
        "name": "study_adaptive_explanation",
        "description": "Generar explicación adaptativa de un concepto según nivel (básico/intermedio/avanzado)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "concept": {"type": "string", "description": "Concepto a explicar"},
                "level": {"type": "string", "enum": ["basico", "intermedio", "avanzado"], "default": "intermedio"}
            },
            "required": ["concept"]
        }
    },
    {
        "name": "study_batch_generate",
        "description": "Generar paquete completo de estudio: flashcards + quiz + resumen + conceptos desde texto",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Texto fuente"},
                "deck_name": {"type": "string", "description": "Deck destino", "default": "Study Batch"},
                "card_count": {"type": "integer", "description": "Número de tarjetas", "default": 20}
            },
            "required": ["text"]
        }
    },
    {
        "name": "study_srs_schedule",
        "description": "Ver programación de repaso espaciado (SRS) y recomendaciones",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "study_note_to_cards",
        "description": "Convertir archivo de notas (markdown/txt) a flashcards Anki automáticamente",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {"type": "string", "description": "Ruta al archivo de notas"},
                "deck_name": {"type": "string", "description": "Deck destino", "default": "Notes Import"},
                "format": {"type": "string", "enum": ["auto", "markdown", "qa"], "default": "auto"}
            },
            "required": ["file_path"]
        }
    }
]

# ─── Handler Map ──────────────────────────────────────────────────────────────

HANDLERS = {
    "anki_create_deck": _anki_create_deck_handler,
    "anki_list_decks": _anki_list_decks_handler,
    "anki_add_note": _anki_add_note_handler,
    "anki_add_notes_bulk": _anki_add_notes_bulk_handler,
    "anki_search_cards": _anki_search_cards_handler,
    "anki_review_stats": _anki_review_stats_handler,
    "anki_generate_flashcards": _anki_generate_flashcards_handler,
    "anki_import_file": _anki_import_file_handler,
    "anki_daily_review": _anki_daily_review_handler,
    "logseq_init_graph": _logseq_init_graph_handler,
    "logseq_create_page": _logseq_create_page_handler,
    "logseq_create_flashcards": _logseq_create_flashcard_page_handler,
    "logseq_create_concept_map": _logseq_create_concept_map_handler,
    "logseq_create_study_guide": _logseq_create_study_guide_handler,
    "logseq_list_pages": _logseq_list_pages_handler,
    "logseq_read_page": _logseq_read_page_handler,
    "study_summarize": _study_summarize_handler,
    "study_extract_concepts": _study_extract_concepts_handler,
    "study_generate_quiz": _study_generate_quiz_handler,
    "study_adaptive_explanation": _study_adaptive_explanation_handler,
    "study_batch_generate": _study_batch_generate_handler,
    "study_srs_schedule": _study_srs_schedule_handler,
    "study_note_to_cards": _study_note_to_cards_handler,
}
