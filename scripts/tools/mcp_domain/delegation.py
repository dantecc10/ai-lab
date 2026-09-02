"""Subagent delegation and task planning tools"""

import os
import subprocess
import json
from mcp_common.paths import HOME
from mcp_common.logging import log_operation

E4B_URL = "http://localhost:9091/v1/chat/completions"
E4B_MODEL = "/home/darkseid/llama.cpp/ai-models/google_gemma-4-E4B-it-Q4_K_M.gguf"

TOOLS = [
    {
        "name": "delegate_to_subagent",
        "description": "Delega una tarea simple al sub-agente E4B (CPU). Útil para tools de Spotify, Kasa, info del sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Instrucción a delegar al sub-agente."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "plan_tasks",
        "description": "Genera plan de tareas para un objetivo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "objective": {
                    "type": "string",
                    "description": "Objetivo a planificar."
                },
                "context": {
                    "type": "string",
                    "description": "Contexto adicional."
                },
                "max_tasks": {
                    "type": "integer",
                    "description": "Máximo de tareas.",
                    "default": 10
                }
            },
            "required": ["objective"]
        }
    },
]

# ── Handlers ───────────────────────────────────────────────
def _delegate_to_subagent_handler(query: str) -> str:
    try:
        payload = {
            "model": E4B_MODEL,
            "messages": [{"role": "user", "content": query}],
            "tools": [
                {"type": "function", "function": {"name": "spotify_search", "description": "Busca en Spotify", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                {"type": "function", "function": {"name": "spotify_play_track", "description": "Reproduce una canción", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
                {"type": "function", "function": {"name": "spotify_play_artist", "description": "Reproduce un artista", "parameters": {"type": "object", "properties": {"artist": {"type": "string"}}, "required": ["artist"]}}},
                {"type": "function", "function": {"name": "spotify_now", "description": "Ver qué suena", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "spotify_play", "description": "Reanudar", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "spotify_pause", "description": "Pausar", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "spotify_next", "description": "Siguiente", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "spotify_previous", "description": "Anterior", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "get_plugs_status", "description": "Estado de enchufes Kasa", "parameters": {"type": "object", "properties": {}}}},
                {"type": "function", "function": {"name": "set_plug_state", "description": "Encender/apagar enchufe", "parameters": {"type": "object", "properties": {"device_name": {"type": "string"}, "turn_on": {"type": "boolean"}}, "required": ["device_name", "turn_on"]}}}
            ],
            "max_tokens": 500
        }

        response = subprocess.run(
            ["curl", "-s", "-X", "POST", E4B_URL,
             "-H", "Content-Type: application/json",
             "-d", json.dumps(payload)],
            capture_output=True, text=True, timeout=60
        )

        if response.returncode != 0:
            return f"Error conectando al sub-agente: {response.stderr}"

        data = json.loads(response.stdout)
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        tool_calls = message.get("tool_calls", [])
        content = message.get("content", "")

        if tool_calls:
            tc = tool_calls[0]
            fn_name = tc["function"]["name"]
            fn_args = json.loads(tc["function"]["arguments"])

            try:
                from mcp_domain.spotify import HANDLERS as SPOTIFY_HANDLERS
                from mcp_domain.smart_home import HANDLERS as HOME_HANDLERS
                all_handlers = {**SPOTIFY_HANDLERS, **HOME_HANDLERS}
            except ImportError:
                all_handlers = {}

            canonical = {
                "get_plugs_status": "kasa_get_plugs_status",
                "set_plug_state": "kasa_set_plug_state",
            }
            dispatch_name = canonical.get(fn_name, fn_name)

            if dispatch_name in all_handlers:
                result = all_handlers[dispatch_name](**fn_args)
            else:
                result = f"Tool desconocido: {fn_name}"

            log_operation("delegate_to_subagent", {"query": query}, f"{fn_name}: {result[:100]}")
            return f"[Sub-agente E4B] {result}"

        log_operation("delegate_to_subagent", {"query": query}, content[:100])
        return f"[Sub-agente E4B] {content}"

    except json.JSONDecodeError:
        return "Error parseando respuesta del sub-agente"
    except subprocess.TimeoutExpired:
        return "Timeout: el sub-agente tardó demasiado"
    except Exception as e:
        return f"Error delegando al sub-agente: {e}"


# ── Email Implementations ──────────────────────────────────

def _plan_tasks_handler(objective: str, context: str = None, max_tasks: int = 10) -> str:
    """Generate task plan for an objective."""
    try:
        output = f"📋 Plan de Tareas: {objective}\n\n"
        
        if context:
            output += f"Contexto: {context}\n\n"
        
        # This is a basic template - the LLM will enhance it
        output += "Tareas sugeridas:\n\n"
        output += "1. 🔍 Definir alcance y requisitos\n"
        output += "2. 📊 Analizar recursos disponibles\n"
        output += "3. 🎯 Identificar dependencias\n"
        output += "4. 📝 Crear tareas detalladas\n"
        output += "5. ⏰ Estimar tiempos\n"
        output += "6. 🚀 Ejecutar en orden de prioridad\n"
        output += "7. ✅ Verificar resultados\n"
        output += "8. 📄 Documentar aprendizajes\n"
        
        return output
    
    except Exception as e:
        return f"Error generando plan: {e}"


# ── Enhanced Communication Implementations ──────────────────

HANDLERS = {
    "delegate_to_subagent": _delegate_to_subagent_handler,
    "plan_tasks": _plan_tasks_handler,
}
