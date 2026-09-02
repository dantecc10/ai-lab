#!/usr/bin/env python3
"""
AI Lab — Knowledge Graph & Dynamic Directives Engine 2.0 (Cognitive Memory)
Provee:
  1. Almacenamiento relacional de entidades y alias en sub-milisegundos.
  2. Grafo multi-hop de conexiones (2-hop / 3-hop traversal).
  3. Memoria temporal con decaimiento cognitivo y TTL.
  4. Mapeo de topología de infraestructura de desarrollo (Developer Mind-Map).
  5. Vinculación con perfiles de voz y directivas operativas.
"""

import os
import sys
import json
import sqlite3
import re
import math
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple, Set

DEFAULT_GRAPH_DIR = Path.home() / ".local" / "share" / "ai-lab" / "memory"
DEFAULT_GRAPH_DB = DEFAULT_GRAPH_DIR / "knowledge_graph.db"


def normalize_term(term: str) -> str:
    """Normaliza un término para búsqueda insensible a acentos, mayúsculas y signos."""
    if not term:
        return ""
    t = term.lower().strip()
    replacements = {
        "á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u",
        "ü": "u", "ñ": "n", '"': "", "'": "", "“": "", "”": "", "«": "", "»": ""
    }
    for orig, rep in replacements.items():
        t = t.replace(orig, rep)
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(t.split())


class KnowledgeGraphEngine:
    """Motor de Grafo de Conocimiento y Directivas Operativas JIT."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or DEFAULT_GRAPH_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA foreign_keys=ON;")
        return conn

    def _init_database(self):
        with self._get_connection() as conn:
            conn.executescript("""
                -- 1. Tabla de Entidades con soporte temporal y acústico
                CREATE TABLE IF NOT EXISTS entities (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL UNIQUE,
                    name_normalized TEXT NOT NULL,
                    entity_type TEXT NOT NULL, -- 'person', 'team', 'place', 'concept', 'project', 'server', 'device'
                    summary TEXT,
                    is_permanent INTEGER DEFAULT 1, -- 1=permanente, 0=efímero con decaimiento
                    decay_days INTEGER DEFAULT 0,   -- Días antes de expirar si no es permanente
                    access_count INTEGER DEFAULT 0,
                    last_accessed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    voice_profile_id TEXT,          -- Vinculación con perfil de voz
                    metadata_json TEXT,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                -- 2. Tabla de Alias y Apodos (Resolución JIT)
                CREATE TABLE IF NOT EXISTS entity_aliases (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id INTEGER NOT NULL,
                    alias TEXT NOT NULL,
                    alias_normalized TEXT NOT NULL UNIQUE,
                    FOREIGN KEY (entity_id) REFERENCES entities(id) ON DELETE CASCADE
                );

                -- 3. Tabla de Relaciones Multi-Hop (Tripletas)
                CREATE TABLE IF NOT EXISTS relations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_id INTEGER NOT NULL,
                    relation_type TEXT NOT NULL, -- 'MEJOR_AMIGO_DE', 'CAPITAN_DE', 'ALOJADO_EN', 'CORRE_EN', etc.
                    target_id INTEGER NOT NULL,
                    description TEXT,
                    weight REAL DEFAULT 1.0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (source_id) REFERENCES entities(id) ON DELETE CASCADE,
                    FOREIGN KEY (target_id) REFERENCES entities(id) ON DELETE CASCADE,
                    UNIQUE(source_id, relation_type, target_id)
                );

                -- 4. Tabla de Directivas de Comportamiento y Reglas Aprendidas
                CREATE TABLE IF NOT EXISTS directives (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL, -- 'methodology', 'preference', 'protocol', 'tone'
                    directive TEXT NOT NULL UNIQUE,
                    rationale TEXT,
                    active INTEGER DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_entities_normalized ON entities(name_normalized);
                CREATE INDEX IF NOT EXISTS idx_aliases_normalized ON entity_aliases(alias_normalized);
                CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
                CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
                CREATE INDEX IF NOT EXISTS idx_directives_active ON directives(active);
            """)

            # Migración segura si las columnas no existían
            try:
                conn.execute("ALTER TABLE entities ADD COLUMN is_permanent INTEGER DEFAULT 1;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE entities ADD COLUMN decay_days INTEGER DEFAULT 0;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE entities ADD COLUMN voice_profile_id TEXT;")
            except Exception:
                pass
            try:
                conn.execute("ALTER TABLE relations ADD COLUMN weight REAL DEFAULT 1.0;")
            except Exception:
                pass

    # =========================================================================
    # GESTIÓN DE ENTIDADES, TEMPORALIDAD Y ALIAS
    # =========================================================================

    def save_entity(
        self,
        name: str,
        entity_type: str,
        summary: str = "",
        aliases: List[str] = None,
        is_permanent: bool = True,
        decay_days: int = 0,
        voice_profile_id: Optional[str] = None,
        metadata: dict = None
    ) -> int:
        """Guarda o actualiza una entidad con sus alias y parámetros temporales."""
        name = name.strip()
        norm_name = normalize_term(name)
        aliases = aliases or []
        meta_str = json.dumps(metadata or {}, ensure_ascii=False)

        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO entities (
                    name, name_normalized, entity_type, summary, is_permanent,
                    decay_days, voice_profile_id, metadata_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    entity_type=excluded.entity_type,
                    summary=CASE WHEN excluded.summary != '' THEN excluded.summary ELSE entities.summary END,
                    is_permanent=excluded.is_permanent,
                    decay_days=excluded.decay_days,
                    voice_profile_id=COALESCE(excluded.voice_profile_id, entities.voice_profile_id),
                    metadata_json=excluded.metadata_json,
                    updated_at=CURRENT_TIMESTAMP
                RETURNING id;
                """,
                (name, norm_name, entity_type, summary, 1 if is_permanent else 0, decay_days, voice_profile_id, meta_str)
            )
            entity_id = cursor.fetchone()["id"]

            all_aliases = set(aliases + [name])
            for alias in all_aliases:
                alias = alias.strip()
                if not alias:
                    continue
                norm_alias = normalize_term(alias)
                conn.execute(
                    """
                    INSERT INTO entity_aliases (entity_id, alias, alias_normalized)
                    VALUES (?, ?, ?)
                    ON CONFLICT(alias_normalized) DO UPDATE SET entity_id=excluded.entity_id;
                    """,
                    (entity_id, alias, norm_alias)
                )

            return entity_id

    def add_relation(self, source_name: str, relation_type: str, target_name: str, description: str = "", weight: float = 1.0) -> bool:
        """Crea una relación dirigida entre dos entidades."""
        rel_type = relation_type.upper().replace(" ", "_")
        with self._get_connection() as conn:
            # Obtener o crear source
            src_cur = conn.execute("SELECT id FROM entities WHERE name_normalized = ?", (normalize_term(source_name),))
            src_row = src_cur.fetchone()
            if not src_row:
                src_id = self.save_entity(source_name, "concept", f"Entidad creada automáticamente: {source_name}")
            else:
                src_id = src_row["id"]

            # Obtener o crear target
            tgt_cur = conn.execute("SELECT id FROM entities WHERE name_normalized = ?", (normalize_term(target_name),))
            tgt_row = tgt_cur.fetchone()
            if not tgt_row:
                tgt_id = self.save_entity(target_name, "concept", f"Entidad creada automáticamente: {target_name}")
            else:
                tgt_id = tgt_row["id"]

            conn.execute(
                """
                INSERT INTO relations (source_id, relation_type, target_id, description, weight)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id, relation_type, target_id) DO UPDATE SET
                    description=excluded.description,
                    weight=excluded.weight;
                """,
                (src_id, rel_type, tgt_id, description, weight)
            )
            return True

    # =========================================================================
    # RAZONAMIENTO MULTI-HOP (GRAFO EN PROFUNDIDAD)
    # =========================================================================

    def traverse_graph(self, entity_name: str, max_hops: int = 2) -> Dict[str, Any]:
        """
        Navega el grafo relacional hasta max_hops grados de separación
        para descubrir conexiones indirectas y razonamiento contextual.
        """
        norm = normalize_term(entity_name)
        with self._get_connection() as conn:
            # Buscar ID de la entidad por coincidencia exacta
            cur = conn.execute(
                """
                SELECT e.id, e.name, e.entity_type, e.summary FROM entities e
                WHERE e.name_normalized = ?
                UNION
                SELECT e.id, e.name, e.entity_type, e.summary FROM entity_aliases a
                JOIN entities e ON a.entity_id = e.id
                WHERE a.alias_normalized = ?
                LIMIT 1
                """,
                (norm, norm)
            )
            root = cur.fetchone()
            if not root:
                # Fallback por coincidencia parcial
                cur_like = conn.execute(
                    """
                    SELECT e.id, e.name, e.entity_type, e.summary FROM entity_aliases a
                    JOIN entities e ON a.entity_id = e.id
                    WHERE a.alias_normalized LIKE '%' || ? || '%'
                    LIMIT 1
                    """,
                    (norm,)
                )
                root = cur_like.fetchone()

            if not root:
                return {"root": None, "nodes": [], "edges": []}

            root_id = root["id"]
            visited_nodes: Dict[int, Dict[str, Any]] = {
                root_id: {"id": root_id, "name": root["name"], "type": root["entity_type"], "summary": root["summary"], "hop": 0}
            }
            edges: List[Dict[str, Any]] = []

            current_level = {root_id}

            for hop in range(1, max_hops + 1):
                next_level = set()
                for node_id in current_level:
                    # Relaciones salientes
                    out_cur = conn.execute(
                        """
                        SELECT r.relation_type, r.description, r.weight, e.id as target_id, e.name, e.entity_type, e.summary
                        FROM relations r
                        JOIN entities e ON r.target_id = e.id
                        WHERE r.source_id = ?
                        """,
                        (node_id,)
                    )
                    for r in out_cur.fetchall():
                        t_id = r["target_id"]
                        edges.append({
                            "source": visited_nodes[node_id]["name"],
                            "relation": r["relation_type"],
                            "target": r["name"],
                            "description": r["description"],
                            "hop": hop
                        })
                        if t_id not in visited_nodes:
                            visited_nodes[t_id] = {
                                "id": t_id, "name": r["name"], "type": r["entity_type"], "summary": r["summary"], "hop": hop
                            }
                            next_level.add(t_id)

                    # Relaciones entrantes
                    in_cur = conn.execute(
                        """
                        SELECT r.relation_type, r.description, r.weight, e.id as source_id, e.name, e.entity_type, e.summary
                        FROM relations r
                        JOIN entities e ON r.source_id = e.id
                        WHERE r.target_id = ?
                        """,
                        (node_id,)
                    )
                    for r in in_cur.fetchall():
                        s_id = r["source_id"]
                        edges.append({
                            "source": r["name"],
                            "relation": r["relation_type"],
                            "target": visited_nodes[node_id]["name"],
                            "description": r["description"],
                            "hop": hop
                        })
                        if s_id not in visited_nodes:
                            visited_nodes[s_id] = {
                                "id": s_id, "name": r["name"], "type": r["entity_type"], "summary": r["summary"], "hop": hop
                            }
                            next_level.add(s_id)

                current_level = next_level
                if not current_level:
                    break

            return {
                "root": dict(root),
                "nodes": list(visited_nodes.values()),
                "edges": edges
            }

    # =========================================================================
    # DECAIMIENTO TEMPORAL Y MANTENIMIENTO COGNITIVO
    # =========================================================================

    def prune_expired_entities(self) -> int:
        """Elimina entidades efímeras cuya vida útil (TTL) haya expirado sin accesos recientes."""
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                DELETE FROM entities
                WHERE is_permanent = 0
                  AND decay_days > 0
                  AND datetime(last_accessed_at, '+' || decay_days || ' days') < datetime('now');
                """
            )
            pruned_count = cursor.rowcount
            return pruned_count

    # =========================================================================
    # GESTIÓN DE DIRECTIVAS
    # =========================================================================

    def save_directive(self, directive: str, category: str = "methodology", rationale: str = "") -> int:
        """Registra o actualiza una directiva de comportamiento de alto nivel."""
        directive = directive.strip()
        with self._get_connection() as conn:
            cursor = conn.execute(
                """
                INSERT INTO directives (category, directive, rationale, active)
                VALUES (?, ?, ?, 1)
                ON CONFLICT(directive) DO UPDATE SET
                    category=excluded.category,
                    rationale=excluded.rationale,
                    active=1
                RETURNING id;
                """,
                (category, directive, rationale)
            )
            return cursor.fetchone()["id"]

    def list_active_directives(self, category: Optional[str] = None) -> List[Dict[str, Any]]:
        """Obtiene todas las directivas activas."""
        with self._get_connection() as conn:
            if category:
                cur = conn.execute("SELECT * FROM directives WHERE active = 1 AND category = ? ORDER BY id ASC", (category,))
            else:
                cur = conn.execute("SELECT * FROM directives WHERE active = 1 ORDER BY id ASC")
            return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # RESOLUCIÓN JUST-IN-TIME (JIT) MULTI-HOP
    # =========================================================================

    def resolve_prompt_context(self, user_prompt: str, enable_multi_hop: bool = True) -> Dict[str, Any]:
        """
        Analiza el prompt en microsegundos y extrae entidades, alias y subgrafos multi-hop
        únicamente si son mencionados en el texto.
        """
        if not user_prompt:
            return {"directives": self.list_active_directives(), "resolved_entities": []}

        norm_prompt = normalize_term(user_prompt)
        words = set(norm_prompt.split())

        matched_entity_ids = set()

        with self._get_connection() as conn:
            cur_aliases = conn.execute("SELECT entity_id, alias, alias_normalized FROM entity_aliases")
            for row in cur_aliases.fetchall():
                alias_norm = row["alias_normalized"]
                if " " in alias_norm:
                    if alias_norm in norm_prompt:
                        matched_entity_ids.add(row["entity_id"])
                else:
                    if alias_norm in words:
                        matched_entity_ids.add(row["entity_id"])

            resolved = []
            for eid in matched_entity_ids:
                e_cur = conn.execute("SELECT * FROM entities WHERE id = ?", (eid,))
                e_row = e_cur.fetchone()
                if not e_row:
                    continue

                # Actualizar conteo de acceso
                conn.execute("UPDATE entities SET access_count = access_count + 1, last_accessed_at = CURRENT_TIMESTAMP WHERE id = ?", (eid,))

                # Alias de la entidad
                a_cur = conn.execute("SELECT alias FROM entity_aliases WHERE entity_id = ?", (eid,))
                aliases = [r["alias"] for r in a_cur.fetchall()]

                # Grafo Multi-Hop si está activo
                subgraph = None
                if enable_multi_hop:
                    subgraph = self.traverse_graph(e_row["name"], max_hops=2)

                resolved.append({
                    "id": e_row["id"],
                    "name": e_row["name"],
                    "type": e_row["entity_type"],
                    "summary": e_row["summary"],
                    "is_permanent": bool(e_row["is_permanent"]),
                    "aliases": aliases,
                    "relations": (subgraph.get("edges", []) if subgraph else []),
                    "subgraph": subgraph
                })

            directives = self.list_active_directives()

            return {
                "directives": directives,
                "resolved_entities": resolved
            }

    def format_jit_context_block(self, user_prompt: str) -> str:
        """Formatea el bloque contextual optimizado para inyectar en el LLM."""
        data = self.resolve_prompt_context(user_prompt, enable_multi_hop=True)
        directives = data.get("directives", [])
        entities = data.get("resolved_entities", [])

        blocks = []

        if directives:
            dir_lines = [f"- {d['directive']}" for d in directives]
            blocks.append("### 🧠 Directivas y Metodologías Aprendidas:\n" + "\n".join(dir_lines))

        if entities:
            ent_lines = []
            for e in entities:
                alias_str = f" (Alias: {', '.join(e['aliases'])})" if len(e['aliases']) > 1 else ""
                desc = f"• **{e['name']}** [{e['type']}]{alias_str}: {e['summary']}"
                
                # Formatear conexiones del subgrafo
                if e.get("subgraph") and e["subgraph"].get("edges"):
                    edges = e["subgraph"]["edges"]
                    rel_items = []
                    for edge in edges[:4]:  # Top 4 conexiones más relevantes
                        rel_items.append(f"{edge['source']} --[{edge['relation']}]--> {edge['target']}")
                    if rel_items:
                        desc += f"\n    ↳ Red de Conexiones: {'; '.join(rel_items)}"

                ent_lines.append(desc)

            blocks.append("### 🔍 Entidades y Relaciones Relevantes Detectadas (JIT):\n" + "\n".join(ent_lines))

        return "\n\n".join(blocks).strip()

    # =========================================================================
    # SEEDER: TOPOLOGÍA DE INFRAESTRUCTURA DE DESARROLLO (MIND-MAP)
    # =========================================================================

    def seed_developer_infrastructure(self):
        """Pre-carga la topología de servidores, servicios y hardware en el Grafo de Conocimiento."""
        # 1. Host local
        self.save_entity(
            name="Pop!_OS Host",
            entity_type="server",
            summary="Sistema operativo host en PC local con procesador AMD Ryzen (16 hilos) y 16GB RAM.",
            aliases=["Pop OS", "mi PC", "mi laptop", "sistema local"]
        )

        # 2. GPU
        self.save_entity(
            name="NVIDIA RTX 5060 Laptop GPU",
            entity_type="device",
            summary="GPU dedicada de 8GB VRAM configurada con aceleración CUDA para inferencia LLM y TTS.",
            aliases=["RTX 5060", "mi GPU", "la grafica", "tarjeta de video"]
        )

        # 3. Servidor Gemma 4 (:9090)
        self.save_entity(
            name="Gemma 4 Server",
            entity_type="service",
            summary="Servidor de inferencia llama.cpp en puerto 9090 con 64k tokens de contexto, Q8_0 KV Cache y Flash Attention.",
            aliases=["gemma4", "servidor 9090", "llama-server", "puerto 9090"]
        )

        # 4. Servidor Whisper (:9093)
        self.save_entity(
            name="Whisper Server",
            entity_type="service",
            summary="Servidor ASR en puerto 9093 acelerado en CPU con modelos Faster-Whisper y Parakeet V3 TDT.",
            aliases=["whisper", "parakeet", "servidor de audio", "puerto 9093"]
        )

        # 5. VPS Cloud (ai.castelancarpinteyro.com)
        self.save_entity(
            name="VPS Plesk Cloud",
            entity_type="server",
            summary="Servidor VPS en 74.208.62.188 con Plesk, Nginx y contenedor Docker ChatShare.",
            aliases=["el VPS", "castelancarpinteyro.com", "ai.castelancarpinteyro.com", "servidor en la nube"]
        )

        # 6. ChatShare Service
        self.save_entity(
            name="ChatShare Cloud Service",
            entity_type="service",
            summary="Plataforma de compartición pública de conversaciones en https://ai.castelancarpinteyro.com puerto 9095.",
            aliases=["ChatShare", "chat manager", "sistema de compartir chats"]
        )

        # Relaciones de Infraestructura
        self.add_relation("Gemma 4 Server", "CORRE_EN", "NVIDIA RTX 5060 Laptop GPU", "Inferencia acelerada por GPU")
        self.add_relation("Gemma 4 Server", "ALOJADO_EN", "Pop!_OS Host", "Servicio systemd local")
        self.add_relation("Whisper Server", "ALOJADO_EN", "Pop!_OS Host", "Servicio systemd local en CPU")
        self.add_relation("ChatShare Cloud Service", "ALOJADO_EN", "VPS Plesk Cloud", "Contenedor Docker expuesto en Nginx")

    def get_full_dump(self) -> Dict[str, Any]:
        """Retorna un dump completo estructurado de todas las tablas de la base de datos."""
        with self._get_connection() as conn:
            entities = [dict(r) for r in conn.execute("SELECT * FROM entities ORDER BY id ASC").fetchall()]
            aliases = [dict(r) for r in conn.execute("SELECT a.id, a.alias, e.name as entity_name FROM entity_aliases a JOIN entities e ON a.entity_id = e.id ORDER BY a.entity_id ASC").fetchall()]
            relations = [dict(r) for r in conn.execute("SELECT r.id, s.name as source, r.relation_type, t.name as target, r.description FROM relations r JOIN entities s ON r.source_id = s.id JOIN entities t ON r.target_id = t.id").fetchall()]
            directives = [dict(r) for r in conn.execute("SELECT * FROM directives WHERE active = 1 ORDER BY id ASC").fetchall()]

            return {
                "entities": entities,
                "aliases": aliases,
                "relations": relations,
                "directives": directives
            }


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI Lab — Visualizador de Memoria Cognitiva y Grafo de Conocimiento")
    parser.add_argument("--json", action="store_true", help="Salida en formato JSON estructurado")
    parser.add_argument("--query", "-q", type=str, help="Simular consulta JIT sobre un mensaje")
    parser.add_argument("--seed-infra", action="store_true", help="Pre-cargar topología de servidores e infraestructura")
    parser.add_argument("--traverse", "-t", type=str, help="Navegar grafo multi-hop para una entidad")
    parser.add_argument("--prune", action="store_true", help="Limpiar entidades temporales expiradas")
    args = parser.parse_args()

    kg = KnowledgeGraphEngine()

    if args.seed_infra:
        kg.seed_developer_infrastructure()
        print("✅ Topología de infraestructura pre-cargada en el Grafo de Conocimiento.")

    if args.prune:
        count = kg.prune_expired_entities()
        print(f"🧹 Entidades temporales expiradas eliminadas: {count}")

    if args.traverse:
        res = kg.traverse_graph(args.traverse, max_hops=2)
        print(f"\n🌐 [Grafo Multi-Hop para]: {args.traverse}")
        if not res["root"]:
            print("  (Entidad no encontrada en el grafo)")
        else:
            print(f"  • Nodo Raíz: {res['root']['name']} [{res['root']['entity_type']}]")
            print(f"  • Nodos Conectados ({len(res['nodes'])}):")
            for n in res["nodes"]:
                if n["id"] != res["root"]["id"]:
                    print(f"    - (Salto {n['hop']}) {n['name']} [{n['type']}]: {n['summary']}")
            print(f"  • Conexiones Encontradas ({len(res['edges'])}):")
            for e in res["edges"]:
                print(f"    ↳ {e['source']} --[{e['relation']}]--> {e['target']}")
        print()
        return

    if args.query:
        print(f"\n🔍 [Prueba JIT para]: \"{args.query}\"")
        block = kg.format_jit_context_block(args.query)
        if block:
            print("\n" + block + "\n")
        else:
            print("→ Ninguna entidad ni directiva relevante detectada.")
        return

    data = kg.get_full_dump()

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return

    print("\n" + "=" * 70)
    print("🧠 AI LAB — COGNITIVE MEMORY ENGINE 2.0 (GRAFO & DIRECTIVAS JIT)")
    print(f"📁 Base de datos: {kg.db_path}")
    print("=" * 70)

    print(f"\n📋 [1] DIRECTIVAS Y METODOLOGÍAS ACTIVAS ({len(data['directives'])}):")
    if not data["directives"]:
        print("  (Sin directivas registradas)")
    for d in data["directives"]:
        print(f"  • [{d['category'].upper()}] {d['directive']}")
        if d.get("rationale"):
            print(f"    ↳ Razón: {d['rationale']}")

    print(f"\n👥 [2] ENTIDADES Y TOPOLOGÍA REGISTRADAS ({len(data['entities'])}):")
    if not data["entities"]:
        print("  (Sin entidades registradas)")
    for e in data["entities"]:
        ent_aliases = [a["alias"] for a in data["aliases"] if a["entity_name"] == e["name"] and a["alias"] != e["name"]]
        alias_txt = f" (Alias: {', '.join(ent_aliases)})" if ent_aliases else ""
        perm_txt = " [Permanente]" if e.get("is_permanent", 1) else f" [TTL: {e.get('decay_days', 0)}d]"
        print(f"  • [{e['entity_type'].upper()}]{perm_txt} {e['name']}{alias_txt}")
        if e.get("summary"):
            print(f"    ↳ Resumen: {e['summary']}")

    print(f"\n🔗 [3] RELACIONES DEL GRAFO ({len(data['relations'])}):")
    if not data["relations"]:
        print("  (Sin relaciones registradas)")
    for r in data["relations"]:
        desc = f" ({r['description']})" if r.get("description") else ""
        print(f"  • {r['source']} --[{r['relation_type']}]--> {r['target']}{desc}")

    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
