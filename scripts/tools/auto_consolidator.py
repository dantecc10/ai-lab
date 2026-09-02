#!/usr/bin/env python3
"""
AI Lab — Proactive Memory Auto-Consolidator (Zero-Effort Cognitive Extractor)
Analiza automáticamente conversaciones recientes en segundo plano y extrae:
  - Entidades y personas con sus alias y apodos.
  - Relaciones y roles (amigos, equipos, funciones).
  - Directivas de comportamiento y preferencias metodológicas.
  - Hechos temporales con TTL.
"""

import os
import sys
import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.tools.knowledge_graph import KnowledgeGraphEngine, normalize_term


class MemoryAutoConsolidator:
    """Motor de extracción heurística y consolidación automática en segundo plano."""

    def __init__(self, kg: Optional[KnowledgeGraphEngine] = None):
        self.kg = kg or KnowledgeGraphEngine()

    def process_conversation_messages(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Procesa una lista de mensajes (turnos de usuario y asistente) y consolida automáticamente
        nuevos conocimientos en el Grafo de Conocimiento.
        """
        extracted = {
            "entities_saved": [],
            "relations_saved": [],
            "directives_saved": []
        }

        user_texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        full_dialogue = "\n".join(user_texts)

        # 1. Extracción de Directivas de Comportamiento
        directives = self._extract_directives(user_texts)
        for d in directives:
            did = self.kg.save_directive(d["directive"], category=d["category"], rationale=d.get("rationale", ""))
            extracted["directives_saved"].append({"id": did, "directive": d["directive"]})

        # 2. Extracción de Entidades, Amigos y Apodos
        entities_data = self._extract_entities_and_aliases(full_dialogue)
        for ent in entities_data:
            eid = self.kg.save_entity(
                name=ent["name"],
                entity_type=ent["type"],
                summary=ent["summary"],
                aliases=ent["aliases"],
                is_permanent=ent["is_permanent"],
                decay_days=ent["decay_days"]
            )
            extracted["entities_saved"].append({"id": eid, "name": ent["name"], "aliases": ent["aliases"]})

            # Relaciones asociadas a la entidad
            for rel in ent.get("relations", []):
                self.kg.add_relation(rel["source"], rel["relation"], rel["target"], rel.get("description", ""))
                extracted["relations_saved"].append(rel)

        return extracted

    def _extract_directives(self, user_texts: List[str]) -> List[Dict[str, Any]]:
        """Identifica directivas metodológicas o reglas de comportamiento emitidas por el usuario."""
        directives = []
        directive_patterns = [
            r"(?:deberías|debes|quiero que|te pido que)\s+(?:aprender a|siempre|acostumbrarte a|considerar)\s+([^.!?\n]+)",
            r"(?:a partir de ahora|de ahora en adelante|en adelante)\s+([^.!?\n]+)",
            r"(?:directiva|regla permanente|metodología):\s*([^.!?\n]+)",
            r"(?:es mejor|prefiero que)\s+(?:tener|hacer|guardar)\s+([^.!?\n]+)"
        ]

        for text in user_texts:
            for pat in directive_patterns:
                matches = re.finditer(pat, text, re.IGNORECASE)
                for m in matches:
                    clean = m.group(0).strip()
                    if len(clean) > 10 and not any(d["directive"].lower() == clean.lower() for d in directives):
                        directives.append({
                            "directive": clean.capitalize(),
                            "category": "methodology",
                            "rationale": f"Directiva detectada en diálogo del usuario: '{text[:60]}...'"
                        })

        return directives

    def _extract_entities_and_aliases(self, text: str) -> List[Dict[str, Any]]:
        """Extrae personas, alias, apodos y conceptos mediante reconocimiento de patrones en español."""
        results = []

        # Patrón 1: "X es mi [mejor amigo / hermano / etc.]"
        rel_pattern = re.compile(
            r"([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)*)\s+es\s+mi\s+(mejor amigo|amigo|hermano|primo|compañero|colega|jefe|pareja)",
            re.IGNORECASE
        )
        for m in rel_pattern.finditer(text):
            name = m.group(1).strip()
            role = m.group(2).strip().lower()
            
            # Buscar apodos cercanos asociados a este nombre
            aliases = self._extract_nearby_aliases(text, name)

            results.append({
                "name": name,
                "type": "person",
                "summary": f"{role.capitalize()} del usuario.",
                "aliases": aliases,
                "is_permanent": True,
                "decay_days": 0,
                "relations": [
                    {"source": name, "relation": f"ES_{role.upper().replace(' ', '_')}_DE", "target": "Usuario", "description": f"{role.capitalize()} del usuario"}
                ]
            })

        # Patrón 2: Equipos y Capitanías
        team_pattern = re.compile(r"equipo(?:\s+de\s+fútbol)?\s+['\"]?([A-ZÁÉÍÓÚÑ0-9\s]+)['\"]?", re.IGNORECASE)
        for m in team_pattern.finditer(text):
            team_name = m.group(1).strip()
            if len(team_name) > 2:
                results.append({
                    "name": team_name,
                    "type": "team",
                    "summary": f"Equipo deportivo del usuario.",
                    "aliases": [team_name],
                    "is_permanent": True,
                    "decay_days": 0,
                    "relations": []
                })

        return results

    def _extract_nearby_aliases(self, text: str, entity_name: str) -> List[str]:
        """Extrae apodos listados o entrecomillados asociados a una entidad."""
        aliases = [entity_name]
        # Buscar patrones como: llamarlo X, Y o Z / apodo "X"
        alias_pattern = re.compile(
            r"(?:llamarlo|llamarle|le dicen|apodado|apodo|como)\s+([^.\n]+)",
            re.IGNORECASE
        )
        for m in alias_pattern.finditer(text):
            chunk = m.group(1)
            # Extraer términos entrecomillados
            quoted = re.findall(r"['\"]([^'\"]+)['\"]", chunk)
            for q in quoted:
                if len(q) > 1 and q not in aliases:
                    aliases.append(q.strip())

            # Extraer nombres separados por comas
            items = re.split(r",|\by\b|\bo\b", chunk)
            for item in items:
                clean = item.strip().strip("'\"")
                if 2 <= len(clean) <= 25 and clean not in aliases and not any(w in clean.lower() for w in ["porque", "cuando", "donde", "equipo"]):
                    aliases.append(clean)

        return list(set(aliases))


def main():
    import argparse
    parser = argparse.ArgumentParser(description="AI Lab — Auto-Consolidador Proactivo de Memoria")
    parser.add_argument("--text", "-t", type=str, help="Procesar texto o mensaje individual para auto-consolidación")
    args = parser.parse_args()

    consolidator = MemoryAutoConsolidator()

    if args.text:
        print(f"\n🧠 Analizando texto: \"{args.text}\"")
        res = consolidator.process_conversation_messages([{"role": "user", "content": args.text}])
        print(f"✅ Entidades guardadas: {len(res['entities_saved'])}")
        for e in res["entities_saved"]:
            print(f"  • {e['name']} (Alias: {', '.join(e['aliases'])})")
        print(f"✅ Directivas aprendidas: {len(res['directives_saved'])}")
        for d in res["directives_saved"]:
            print(f"  • {d['directive']}")
        print(f"✅ Relaciones creadas: {len(res['relations_saved'])}")
        for r in res["relations_saved"]:
            print(f"  • {r['source']} -> {r['relation']} -> {r['target']}")
        print()


if __name__ == "__main__":
    main()
