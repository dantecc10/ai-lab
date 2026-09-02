#!/usr/bin/env python3
"""
AI Lab — Declarative DAG Workflow Runner
Ejecuta pipelines de tareas multi-paso con dependencias, interpolación de variables
y manejo de errores.
"""

import os
import sys
import json
import time
import re
import sqlite3
from pathlib import Path
from datetime import datetime

# Rutas de workflows
DEFAULT_WORKFLOW_DIRS = [
    Path.home() / ".config" / "ai-lab" / "workflows",
    Path.home() / "ai-lab" / "configs" / "workflows",
    Path(__file__).resolve().parent.parent.parent / "configs" / "workflows"
]

DB_PATH = Path.home() / ".local" / "share" / "ai-lab" / "workflow_executions.db"

# Inyectar dependencias de tools
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

class DAGRunner:
    """Ejecutor de flujos de trabajo declarativos."""

    def __init__(self, workflow_dirs: list[Path] | None = None):
        self.workflow_dirs = workflow_dirs or DEFAULT_WORKFLOW_DIRS
        for d in self.workflow_dirs:
            d.mkdir(parents=True, exist_ok=True)
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(DB_PATH))
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS workflow_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                workflow_name TEXT NOT NULL,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                finished_at DATETIME,
                status TEXT NOT NULL, -- running, success, failed
                total_steps INTEGER DEFAULT 0,
                completed_steps INTEGER DEFAULT 0,
                results_json TEXT,
                error_message TEXT
            );
            """)
            conn.commit()

    def list_workflows(self) -> list[dict]:
        """Lista todos los workflows disponibles."""
        workflows = []
        seen = set()

        for directory in self.workflow_dirs:
            if not directory.exists():
                continue
            for ext in ("*.json", "*.yaml", "*.yml"):
                for file_path in directory.glob(ext):
                    if file_path.name in seen:
                        continue
                    seen.add(file_path.name)
                    try:
                        wf = self._load_workflow_file(file_path)
                        workflows.append({
                            "name": wf.get("name", file_path.stem),
                            "description": wf.get("description", ""),
                            "file": str(file_path),
                            "steps_count": len(wf.get("steps", []))
                        })
                    except Exception:
                        pass
        return workflows

    def _load_workflow_file(self, file_path: Path) -> dict:
        """Carga workflow desde archivo JSON o YAML."""
        content = file_path.read_text(encoding="utf-8")
        if file_path.suffix == ".json":
            return json.loads(content)
        else:
            # Simple YAML parser fallback si PyYAML no está disponible
            try:
                import yaml
                return yaml.safe_load(content)
            except ImportError:
                # Intentar parsear como JSON si no hay PyYAML
                return json.loads(content)

    def find_workflow(self, name: str) -> tuple[dict | None, Path | None]:
        """Busca un workflow por nombre."""
        for directory in self.workflow_dirs:
            for ext in (".json", ".yaml", ".yml"):
                p = directory / f"{name}{ext}"
                if p.exists():
                    return self._load_workflow_file(p), p
        return None, None

    def _interpolate_args(self, args: dict, context: dict) -> dict:
        """Interpola variables tipo {{step_id.result}} o {{step_id.key}} en argumentos."""
        interpolated = {}
        pattern = re.compile(r"\{\{([^}]+)\}\}")

        for k, v in args.items():
            if isinstance(v, str):
                def replace_var(match):
                    expr = match.group(1).strip()
                    parts = expr.split(".")
                    val = context
                    for part in parts:
                        if isinstance(val, dict):
                            val = val.get(part, "")
                        else:
                            return ""
                    return str(val)
                interpolated[k] = pattern.sub(replace_var, v)
            elif isinstance(v, dict):
                interpolated[k] = self._interpolate_args(v, context)
            else:
                interpolated[k] = v
        return interpolated

    def _execute_tool(self, tool_name: str, arguments: dict) -> str:
        """Ejecuta una herramienta a través del despachador de AI Lab."""
        from scripts.tools.system_mcp_server import handle_request
        req = {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": int(time.time() * 1000)
        }
        res = handle_request(req)
        if res and "result" in res and "content" in res["result"]:
            texts = [c.get("text", "") for c in res["result"]["content"] if c.get("type") == "text"]
            return "\n".join(texts)
        elif res and "error" in res:
            raise RuntimeError(res["error"].get("message", "Error desconocido en tool"))
        return ""

    def run_workflow(self, workflow_name: str, custom_params: dict | None = None) -> dict:
        """Ejecuta un workflow completo paso a paso."""
        wf_data, path = self.find_workflow(workflow_name)
        if not wf_data:
            raise FileNotFoundError(f"Workflow '{workflow_name}' no encontrado en {self.workflow_dirs}")

        steps = wf_data.get("steps", [])
        run_id = None

        with self._get_connection() as conn:
            cur = conn.execute("""
            INSERT INTO workflow_runs (workflow_name, status, total_steps, completed_steps)
            VALUES (?, 'running', ?, 0)
            """, (workflow_name, len(steps)))
            run_id = cur.lastrowid
            conn.commit()

        context = {"params": custom_params or {}, "env": dict(os.environ)}
        completed = 0
        step_results = {}

        try:
            for step in steps:
                step_id = step.get("id") or f"step_{completed + 1}"
                tool_name = step.get("tool")
                raw_args = step.get("args", {})
                
                # Interpolar variables
                resolved_args = self._interpolate_args(raw_args, context)

                # Ejecutar
                t0 = time.time()
                output = self._execute_tool(tool_name, resolved_args)
                dur_ms = (time.time() - t0) * 1000.0

                step_results[step_id] = {
                    "tool": tool_name,
                    "duration_ms": round(dur_ms, 2),
                    "result": output,
                    "status": "success"
                }
                context[step_id] = step_results[step_id]
                completed += 1

                with self._get_connection() as conn:
                    conn.execute("""
                    UPDATE workflow_runs 
                    SET completed_steps = ?, results_json = ?
                    WHERE id = ?
                    """, (completed, json.dumps(step_results, ensure_ascii=False), run_id))
                    conn.commit()

            # Finalizar con éxito
            with self._get_connection() as conn:
                conn.execute("""
                UPDATE workflow_runs 
                SET status = 'success', finished_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """, (run_id,))
                conn.commit()

            return {
                "run_id": run_id,
                "workflow": workflow_name,
                "status": "success",
                "total_steps": len(steps),
                "completed_steps": completed,
                "results": step_results
            }

        except Exception as e:
            err_msg = str(e)
            with self._get_connection() as conn:
                conn.execute("""
                UPDATE workflow_runs 
                SET status = 'failed', finished_at = CURRENT_TIMESTAMP, error_message = ?
                WHERE id = ?
                """, (err_msg, run_id))
                conn.commit()

            return {
                "run_id": run_id,
                "workflow": workflow_name,
                "status": "failed",
                "total_steps": len(steps),
                "completed_steps": completed,
                "error": err_msg,
                "partial_results": step_results
            }

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="AI Lab — DAG & Automation Workflow Runner")
    parser.add_argument("--list", "-l", action="store_true", help="Listar workflows disponibles")
    parser.add_argument("--run", "-r", type=str, help="Ejecutar un workflow por su nombre")
    args = parser.parse_args()

    runner = DAGRunner()

    if args.run:
        print(f"\n🚀 [Ejecutando Workflow]: {args.run}")
        result = runner.run_workflow(args.run)
        print(f"📊 Estado: {result['status'].upper()} ({result.get('completed_steps', 0)}/{result.get('total_steps', 0)} pasos completados)")
        if result['status'] == 'success':
            print("\n✅ Resultados por Paso:")
            for step_id, info in result.get('results', {}).items():
                print(f"  • [{step_id}] Herramienta '{info['tool']}' ({info['duration_ms']}ms):")
                res_str = str(info.get('result', ''))
                if len(res_str) > 120:
                    res_str = res_str[:120] + "..."
                print(f"    ↳ {res_str}")
        else:
            print(f"❌ Error: {result.get('error')}")
        print()
    else:
        print(f"\n[+] DAGRunner inicializado. Workflows disponibles: {len(runner.list_workflows())}")
        for w in runner.list_workflows():
            print(f"  • {w['name']}: {w['description']} ({w['steps_count']} pasos)")
        print()
