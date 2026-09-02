"""Workflow execution and management tools"""

import os
from mcp_common.paths import HOME
from mcp_common.logging import log_operation

TOOLS = [
    {
        "name": "workflow_list",
        "description": "Lista todos los flujos de trabajo declarativos (DAG pipelines) disponibles en AI Lab.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "workflow_run",
        "description": "Ejecuta un flujo de trabajo declarativo (DAG pipeline) por su nombre (ej: 'daily_briefing', 'system_health_audit').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre del workflow a ejecutar."
                },
                "params": {
                    "type": "object",
                    "description": "Parámetros personalizados opcionales para el flujo."
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "workflow_status",
        "description": "Consulta el estado y resultados de un flujo de trabajo ejecutado previamente por su ID de ejecución.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {
                    "type": "integer",
                    "description": "ID numérico de la ejecución del workflow."
                }
            },
            "required": ["run_id"]
        }
    },
]

# ── Handlers ───────────────────────────────────────────────
def _workflow_list_handler() -> str:
    """Lista los flujos de trabajo declarativos disponibles."""
    try:
        from scripts.automation.dag_runner import DAGRunner
        runner = DAGRunner()
        wfs = runner.list_workflows()
        if not wfs:
            return "ℹ️ No se encontraron flujos de trabajo registrados en `configs/workflows/`."

        output = f"📋 **Flujos de Trabajo Declarativos ({len(wfs)} disponibles):**\n\n"
        for wf in wfs:
            output += f"• **`{wf['name']}`**: {wf['description']} ({wf['steps_count']} pasos)\n"
            output += f"  └── Archivo: `{wf['file']}`\n"
        return output
    except Exception as e:
        return f"Error al listar workflows: {e}"



def _workflow_run_handler(name: str, params: dict = None) -> str:
    """Ejecuta un flujo de trabajo declarativo por nombre."""
    try:
        from scripts.automation.dag_runner import DAGRunner
        runner = DAGRunner()
        res = runner.run_workflow(name, custom_params=params)

        icon = "✅" if res["status"] == "success" else "❌"
        output = f"{icon} **Ejecución de Workflow: `{name}` (Run #{res['run_id']})**\n\n"
        output += f"• **Estado**: {res['status'].upper()}\n"
        output += f"• **Pasos**: {res['completed_steps']}/{res['total_steps']}\n\n"

        if res.get("error"):
            output += f"⚠️ **Error en ejecución:** {res['error']}\n\n"

        results = res.get("results") or res.get("partial_results") or {}
        output += "📊 **Resultados por Paso:**\n"
        for step_id, step_info in results.items():
            st_icon = "✓" if step_info.get("status") == "success" else "✗"
            dur = step_info.get("duration_ms", 0)
            res_preview = str(step_info.get("result", ""))[:120].replace("\n", " ")
            output += f"  - [{st_icon}] `{step_id}` ({step_info.get('tool')}, {dur}ms): {res_preview}...\n"

        return output
    except Exception as e:
        return f"Error al ejecutar workflow '{name}': {e}"



def _workflow_status_handler(run_id: int) -> str:
    """Consulta el estado de una ejecución de workflow."""
    try:
        from scripts.automation.dag_runner import DAGRunner
        runner = DAGRunner()
        with runner._get_connection() as conn:
            row = conn.execute("SELECT * FROM workflow_runs WHERE id = ?", (run_id,)).fetchone()
            if not row:
                return f"Error: No se encontró la ejecución con ID {run_id}."

            icon = "✅" if row["status"] == "success" else ("⏳" if row["status"] == "running" else "❌")
            output = f"{icon} **Workflow Run #{row['id']}: `{row['workflow_name']}`**\n\n"
            output += f"• **Estado**: {row['status']}\n"
            output += f"• **Inicio**: {row['started_at']} | **Fin**: {row['finished_at'] or 'En progreso'}\n"
            output += f"• **Pasos**: {row['completed_steps']}/{row['total_steps']}\n"
            if row["error_message"]:
                output += f"• **Error**: {row['error_message']}\n"
            return output
    except Exception as e:
        return f"Error al consultar estado del workflow: {e}"


# ── Vector Memory & Local RAG Tools ─────────────────────────

HANDLERS = {
    "workflow_list": _workflow_list_handler,
    "workflow_run": _workflow_run_handler,
    "workflow_status": _workflow_status_handler,
}
