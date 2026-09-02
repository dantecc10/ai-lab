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
    "elektrodante": "192.168.1.70",
    "lux": "192.168.1.71"
}

ALIASES = {
    "luz": "lux",
    "foco": "lux",
    "lampara": "lux",
    "electro": "elektrodante",
    "escritorio": "elektrodante",
    "pc": "elektrodante"
}

# ── Funciones Kasa ────────────────────────────────────────
async def get_kasa_devices_map():
    """Descubre dinámicamente dispositivos Kasa en la red o usa la caché conocida."""
    from kasa import Discover
    discovered = {}
    try:
        devs = await asyncio.wait_for(Discover.discover(), timeout=2.5)
        for ip, d in devs.items():
            discovered[d.alias.lower().strip()] = ip
            if d.alias.lower().strip() == "elektrodante":
                DEVICES["elektrodante"] = ip
            elif d.alias.lower().strip() == "lux":
                DEVICES["lux"] = ip
    except Exception:
        pass
    return DEVICES

async def resolve_device(name: str):
    key = name.lower().strip()
    devices = await get_kasa_devices_map()
    if key in devices:
        return key, devices[key]
    if key in ALIASES and ALIASES[key] in devices:
        target = ALIASES[key]
        return target, devices[target]
    return None, None

async def kasa_set_plug_state(device_name: str, turn_on: bool) -> str:
    from kasa import Discover
    if device_name.lower() in ["todo", "todos", "all"]:
        results = []
        devices = await get_kasa_devices_map()
        for dev_name, dev_ip in devices.items():
            try:
                plug = await Discover.discover_single(dev_ip)
                await plug.update()
                if turn_on:
                    await plug.turn_on()
                    results.append(f"{dev_name}: ON")
                else:
                    await plug.turn_off()
                    results.append(f"{dev_name}: OFF")
            except Exception as e:
                results.append(f"{dev_name}: Error ({e})")
        return "Dispositivos actualizados: " + ", ".join(results)

    target, ip = await resolve_device(device_name)
    if not ip:
        return f"Dispositivo '{device_name}' no reconocido. Disponibles: ElektroDante, Lux, todos."

    try:
        plug = await Discover.discover_single(ip)
        await plug.update()
        if turn_on:
            await plug.turn_on()
            return f"'{target}' encendido correctamente."
        else:
            await plug.turn_off()
            return f"'{target}' apagado correctamente."
    except Exception as e:
        return f"Error al cambiar estado de '{target}' ({ip}): {e}"

async def kasa_get_plugs_status() -> str:
    status_list = []
    for name, ip in DEVICES.items():
        plug = SmartPlug(ip)
        await plug.update()
        state_str = "Encendido" if plug.is_on else "Apagado"
        status_list.append(f"{name.capitalize()} ({ip}): {state_str}")
    return "\n".join(status_list)

# ── MCP Tools Definitions ────────────────────────────────
TOOLS = [
    {
        "name": "set_plug_state",
        "description": "Enciende o apaga un enchufe Kasa por nombre (ElektroDante, Lux, todos).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "device_name": {
                    "type": "string",
                    "description": "Nombre del dispositivo: 'elektrodante', 'lux', o 'todos'"
                },
                "turn_on": {
                    "type": "boolean",
                    "description": "True para encender, False para apagar"
                }
            },
            "required": ["device_name", "turn_on"]
        }
    },
    {
        "name": "get_plugs_status",
        "description": "Obtiene el estado actual (encendido/apagado) de todos los enchufes Kasa.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    }
]

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
