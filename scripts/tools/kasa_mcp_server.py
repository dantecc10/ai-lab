#!/usr/bin/env python3
"""
MCP Server para enchufes Kasa — Stdio transport para llama.cpp
Lee JSON-RPC de stdin, escribe respuestas a stdout.
"""

import sys
import json
import asyncio
from kasa import SmartPlug

# ── Configuración ─────────────────────────────────────────
DEVICES = {
    "elektrodante": "192.168.1.66",
    "lux": "192.168.1.67"
}

ALIASES = {
    "luz": "lux",
    "foco": "lux",
    "lampara": "lux",
    "electro": "elektrodante",
    "escritorio": "elektrodante",
    "pc": "elektrodante"
}

# ── Tools disponibles ─────────────────────────────────────
TOOLS = [
    {
        "name": "set_plug_state",
        "description": "Enciende o apaga uno o todos los enchufes inteligentes Kasa.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "Nombre del dispositivo ('ElektroDante', 'Lux', 'todos')."
                },
                "turn_on": {
                    "type": "boolean",
                    "description": "True para encender, False para apagar."
                }
            },
            "required": ["device_name", "turn_on"]
        }
    },
    {
        "name": "get_plugs_status",
        "description": "Obtiene el estado actual de todos los enchufes.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

# ── Funciones Kasa ────────────────────────────────────────
def resolve_device(name: str):
    key = name.lower().strip()
    if key in DEVICES:
        return key, DEVICES[key]
    if key in ALIASES and ALIASES[key] in DEVICES:
        target = ALIASES[key]
        return target, DEVICES[target]
    return None, None

async def kasa_set_plug_state(device_name: str, turn_on: bool) -> str:
    if device_name.lower() in ["todo", "todos", "all"]:
        results = []
        for dev_name, dev_ip in DEVICES.items():
            plug = SmartPlug(dev_ip)
            await plug.update()
            if turn_on:
                await plug.turn_on()
                results.append(f"{dev_name}: ON")
            else:
                await plug.turn_off()
                results.append(f"{dev_name}: OFF")
        return "Dispositivos actualizados: " + ", ".join(results)

    target, ip = resolve_device(device_name)
    if not ip:
        return f"Dispositivo '{device_name}' no reconocido. Disponibles: ElektroDante, Lux, todos."

    plug = SmartPlug(ip)
    await plug.update()
    if turn_on:
        await plug.turn_on()
        return f"'{target}' encendido correctamente."
    else:
        await plug.turn_off()
        return f"'{target}' apagado correctamente."

async def kasa_get_plugs_status() -> str:
    status_list = []
    for name, ip in DEVICES.items():
        plug = SmartPlug(ip)
        await plug.update()
        state_str = "Encendido" if plug.is_on else "Apagado"
        status_list.append(f"{name.capitalize()} ({ip}): {state_str}")
    return "\n".join(status_list)

# ── MCP JSON-RPC Handler ─────────────────────────────────
def handle_request(request: dict) -> dict:
    method = request.get("method")
    req_id = request.get("id")
    params = request.get("params", {})

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "kasa-mcp-server",
                    "version": "1.0.0"
                }
            }
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"tools": TOOLS}
        }

    elif method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        try:
            if tool_name == "set_plug_state":
                result = asyncio.run(kasa_set_plug_state(
                    arguments["device_name"],
                    arguments["turn_on"]
                ))
            elif tool_name == "get_plugs_status":
                result = asyncio.run(kasa_get_plugs_status())
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                }

            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": result}]
                }
            }
        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": f"Error: {str(e)}"}],
                    "isError": True
                }
            }

    elif method == "notifications/initialized":
        # Notification, no response needed
        return None

    else:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"}
        }

# ── Main loop: stdin → stdout ─────────────────────────────
if __name__ == "__main__":
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            continue

        response = handle_request(request)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
