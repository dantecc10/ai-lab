import json
import sys
import httpx
import asyncio
import traceback

BASE_URL = "http://localhost:9095/api/v1"

TOOL_DEFINITIONS = [
    {
        "name": "chat_create",
        "description": "Create a new chat session",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Chat title"},
                "messages": {"type": "array", "description": "Initial messages", "default": []},
                "metadata": {"type": "object", "description": "Additional metadata", "default": {}},
            },
            "required": ["title"],
        },
    },
    {
        "name": "chat_list",
        "description": "List all chats",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 50},
                "offset": {"type": "integer", "default": 0},
            },
        },
    },
    {
        "name": "chat_get",
        "description": "Get a chat with all messages",
        "inputSchema": {
            "type": "object",
            "properties": {"chat_id": {"type": "string"}},
            "required": ["chat_id"],
        },
    },
    {
        "name": "chat_edit",
        "description": "Edit a chat (creates new version)",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
                "messages": {"type": "array"},
                "title": {"type": "string"},
            },
            "required": ["chat_id", "messages"],
        },
    },
    {
        "name": "chat_delete",
        "description": "Soft delete a chat",
        "inputSchema": {
            "type": "object",
            "properties": {"chat_id": {"type": "string"}},
            "required": ["chat_id"],
        },
    },
    {
        "name": "chat_versions",
        "description": "Get version history of a chat",
        "inputSchema": {
            "type": "object",
            "properties": {"chat_id": {"type": "string"}},
            "required": ["chat_id"],
        },
    },
    {
        "name": "chat_branch",
        "description": "Create a branch from a chat",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["chat_id", "name"],
        },
    },
    {
        "name": "chat_share",
        "description": "Share a chat and get access link",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {"type": "string"},
                "expires_hours": {"type": "integer", "default": 72},
                "label": {"type": "string"},
            },
            "required": ["chat_id"],
        },
    },
    {
        "name": "token_revoke",
        "description": "Revoke an access token",
        "inputSchema": {
            "type": "object",
            "properties": {"token_id": {"type": "string"}},
            "required": ["token_id"],
        },
    },
]


async def call_api(method: str, path: str, data: dict = None) -> dict:
    async with httpx.AsyncClient(timeout=10) as client:
        url = f"{BASE_URL}{path}"
        if method == "GET":
            resp = await client.get(url, params=data)
        elif method == "POST":
            resp = await client.post(url, json=data)
        elif method == "PUT":
            resp = await client.put(url, json=data)
        elif method == "DELETE":
            resp = await client.delete(url)
        else:
            return {"error": f"Unknown method: {method}"}

        if resp.status_code >= 400:
            return {"error": resp.text}
        return resp.json()


async def handle_tool(name: str, arguments: dict) -> str:
    try:
        if name == "chat_create":
            result = await call_api("POST", "/chats", arguments)
        elif name == "chat_list":
            result = await call_api("GET", "/chats", arguments)
        elif name == "chat_get":
            result = await call_api("GET", f"/chats/{arguments['chat_id']}")
        elif name == "chat_edit":
            chat_id = arguments.pop("chat_id")
            result = await call_api("PUT", f"/chats/{chat_id}", arguments)
        elif name == "chat_delete":
            result = await call_api("DELETE", f"/chats/{arguments['chat_id']}")
        elif name == "chat_versions":
            result = await call_api("GET", f"/chats/{arguments['chat_id']}/versions")
        elif name == "chat_branch":
            chat_id = arguments.pop("chat_id")
            result = await call_api("POST", f"/chats/{chat_id}/branches", arguments)
        elif name == "chat_share":
            chat_id = arguments.pop("chat_id")
            result = await call_api("POST", f"/chats/{chat_id}/share", arguments)
        elif name == "token_revoke":
            result = await call_api("POST", f"/tokens/{arguments['token_id']}/revoke")
        else:
            result = {"error": f"Unknown tool: {name}"}

        return json.dumps(result)
    except Exception as e:
        return json.dumps({"error": str(e)})


async def handle_request(request: dict) -> dict:
    method = request.get("method")
    req_id = request.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "chat-manager", "version": "1.0.0"},
            },
        }
    elif method == "notifications/initialized":
        return None
    elif method == "tools/list":
        return {"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOL_DEFINITIONS}}
    elif method == "tools/call":
        tool_name = request["params"]["name"]
        arguments = request["params"].get("arguments", {})
        result = await handle_tool(tool_name, arguments)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {"content": [{"type": "text", "text": result}]},
        }
    elif method == "ping":
        return {"jsonrpc": "2.0", "id": req_id, "result": {}}
    else:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": -32601, "message": f"Unknown method: {method}"}}


async def main():
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin.buffer)

    while True:
        try:
            line = await reader.readline()
            if not line:
                break

            line = line.decode().strip()
            if not line:
                continue

            if line.startswith("Content-Length:"):
                length = int(line.split(":")[1].strip())
                await reader.readline()
                body = await reader.readexactly(length)
                request = json.loads(body.decode())
            else:
                request = json.loads(line)

            response = await handle_request(request)
            if response:
                resp_bytes = json.dumps(response).encode()
                sys.stdout.buffer.write(f"Content-Length: {len(resp_bytes)}\r\n\r\n".encode())
                sys.stdout.buffer.write(resp_bytes)
                sys.stdout.buffer.flush()

        except asyncio.CancelledError:
            break
        except Exception:
            traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
