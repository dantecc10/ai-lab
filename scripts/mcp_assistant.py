#!/usr/bin/env python3
"""
Ecosistema MCP Completo - Conecta a llama-server + MCP servers
Uso: python3 mcp_assistant.py [prompt]
     python3 mcp_assistant.py          # modo interactivo
"""

import json
import os
import sys
import subprocess
import signal
from pathlib import Path
from openai import OpenAI

# ── Configuración ────────────────────────────────────────────
LLAMA_URL = os.environ.get("LLAMA_URL", "http://localhost:9090")
MODEL = os.environ.get("MODEL", "/home/darkseid/llama.cpp/ai-models/gemma-4-12b-it-Q4_K_M.gguf")
MCP_CONFIG = Path.home() / ".config" / "mcp-servers.json"
PYTHON_BIN = "/home/darkseid/scripting/gpu-tools/skills/.venv/bin/python3"
SKILLS_DIR = Path.home() / "scripting/gpu-tools/skills"

# ── Colores ──────────────────────────────────────────────────
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    RED = "\033[31m"
    WHITE = "\033[97m"


def banner():
    print(f"""{C.CYAN}{C.BOLD}
╔═══════════════════════════════════════════════════════╗
║           🤖 MCP Ecosistema Completo                 ║
║   llama-server + MCP servers + 140+ herramientas     ║
╚═══════════════════════════════════════════════════════╝{C.RESET}
""")


# ── MCP Client ───────────────────────────────────────────────
class MCPClient:
    """Cliente para comunicarse con un MCP server via subprocess."""

    def __init__(self, name: str, command: list[str]):
        self.name = name
        self.command = command
        self.process = None
        self.tools = []
        self._request_id = 0

    def start(self) -> bool:
        """Inicia el MCP server como subprocess."""
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(SKILLS_DIR),
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )

            # Initialize
            response = self._send("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mcp-assistant", "version": "1.0.0"}
            })

            if not response:
                return False

            # Initialized notification
            self._notify("notifications/initialized", {})

            # Get tools
            tools_response = self._send("tools/list", {})
            if tools_response and "tools" in tools_response:
                self.tools = tools_response["tools"]

            return True

        except Exception as e:
            print(f"{C.RED}Error starting {self.name}: {e}{C.RESET}")
            return False

    def _send(self, method: str, params: dict) -> dict | None:
        """Envía un request y espera respuesta."""
        self._request_id += 1
        request = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self._request_id
        }

        try:
            self.process.stdin.write(json.dumps(request) + "\n")
            self.process.stdin.flush()

            response_line = self.process.stdout.readline()
            if response_line:
                response = json.loads(response_line)
                return response.get("result", response.get("error"))
        except Exception as e:
            print(f"{C.DIM}MCP {self.name} error: {e}{C.RESET}")
        return None

    def _notify(self, method: str, params: dict):
        """Envía una notificación (sin respuesta esperada)."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        self.process.stdin.write(json.dumps(notification) + "\n")
        self.process.stdin.flush()

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Ejecuta una tool en el MCP server."""
        response = self._send("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        if not response:
            return f"Error: No response from {self.name}"

        if "error" in response:
            return f"Error: {response['error']}"

        # Extract content
        content = response.get("content", [])
        if isinstance(content, list):
            texts = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    texts.append(item.get("text", ""))
                elif isinstance(item, str):
                    texts.append(item)
            return "\n".join(texts) if texts else json.dumps(response)

        return str(content)

    def stop(self):
        """Detiene el MCP server."""
        if self.process:
            self.process.stdin.close()
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()


# ── Ecosistema MCP ──────────────────────────────────────────
class MCPEcosystem:
    """Maneja todos los MCP servers y sus herramientas."""

    def __init__(self):
        self.clients: dict[str, MCPClient] = {}
        self.all_tools: list[dict] = []
        self.tool_map: dict[str, MCPClient] = {}

    def load_config(self) -> bool:
        """Carga la configuración de MCP servers."""
        if not MCP_CONFIG.exists():
            print(f"{C.RED}No se encontró {MCP_CONFIG}{C.RESET}")
            return False

        with open(MCP_CONFIG) as f:
            config = json.load(f)

        servers = config.get("mcpServers", {})
        if not servers:
            print(f"{C.RED}No hay MCP servers en la configuración{C.RESET}")
            return False

        for name, server_config in servers.items():
            command = server_config.get("command", "")
            args = server_config.get("args", [])

            if not command:
                continue

            full_command = [command] + args
            self.clients[name] = MCPClient(name, full_command)
            print(f"{C.DIM}  📦 {name}: {command} {' '.join(args[:2])}...{C.RESET}")

        return True

    def start_all(self):
        """Inicia todos los MCP servers."""
        print(f"\n{C.YELLOW}Iniciando MCP servers...{C.RESET}")

        for name, client in self.clients.items():
            sys.stdout.write(f"  ⏳ {name}... ")
            sys.stdout.flush()

            if client.start():
                self.all_tools.extend(client.tools)
                for tool in client.tools:
                    self.tool_map[tool["name"]] = client
                print(f"{C.GREEN}✅ {len(client.tools)} tools{C.RESET}")
            else:
                print(f"{C.RED}❌ Error{C.RESET}")

        print(f"\n{C.GREEN}{C.BOLD}✅ Total: {len(self.all_tools)} herramientas disponibles{C.RESET}")

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Ejecuta una tool en el server MCP apropiado."""
        client = self.tool_map.get(tool_name)
        if not client:
            return f"Error: Tool '{tool_name}' no encontrada"
        return client.call_tool(tool_name, arguments)

    def get_openai_tools(self) -> list[dict]:
        """Convierte las tools MCP a formato OpenAI."""
        openai_tools = []
        for tool in self.all_tools:
            openai_tool = {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
                }
            }
            openai_tools.append(openai_tool)
        return openai_tools

    def stop_all(self):
        """Detiene todos los MCP servers."""
        for client in self.clients.values():
            client.stop()


# ── Asistente ────────────────────────────────────────────────
class Assistant:
    """Asistente que conecta con MCP ecosistema."""

    def __init__(self, ecosystem: MCPEcosystem):
        self.eco = ecosystem
        self.client = OpenAI(
            base_url=f"{LLAMA_URL}/v1",
            api_key="not-needed"
        )
        self.messages = []
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Carga el system prompt."""
        prompt_file = Path.home() / ".config" / "system-prompt.txt"
        if prompt_file.exists():
            return prompt_file.read_text().strip()

        return (
            "Eres un asistente AI local en Pop!_OS. "
            "Tienes acceso a más de 140 herramientas MCP para controlar el sistema, "
            "buscar en internet, gestionar archivos, controlar dispositivos IoT, "
            "realizar OSINT, y mucho más. "
            "Sé conciso y usa las herramientas cuando sea necesario."
        )

    def _build_tools_payload(self) -> list[dict]:
        """Construye el payload de tools para la request."""
        # Limit to 140 tools max (llama.cpp limit)
        tools = self.eco.get_openai_tools()
        return tools[:140]

    def chat(self, user_message: str, max_iterations: int = 10) -> str:
        """Envía un mensaje y procesa tool calls."""
        self.messages.append({"role": "user", "content": user_message})

        tools = self._build_tools_payload()

        for iteration in range(max_iterations):
            # Send to model
            response = self.client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": self.system_prompt}
                ] + self.messages[-20:],  # Keep last 20 messages
                tools=tools,
                tool_choice="auto",
                temperature=0.7
            )

            msg = response.choices[0].message

            if not msg.tool_calls:
                # No more tool calls, return final response
                self.messages.append({"role": "assistant", "content": msg.content})
                return msg.content

            # Process tool calls
            self.messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in msg.tool_calls
                ]
            })

            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                # Execute tool
                print(f"  {C.CYAN}🔧 {fn_name}({', '.join(f'{k}={v}' for k,v in args.items())}){C.RESET}", file=sys.stderr)
                result = self.eco.call_tool(fn_name, args)

                # Truncate long results
                if len(result) > 8000:
                    result = result[:8000] + "\n... (truncado)"

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": result
                })

        return "Se alcanzó el máximo de iteraciones de tool calls."


# ── Main ─────────────────────────────────────────────────────
def main():
    banner()

    # Check server
    try:
        import requests
        r = requests.get(f"{LLAMA_URL}/health", timeout=3)
        if r.status_code != 200:
            print(f"{C.RED}⚠️  llama-server no responde en {LLAMA_URL}{C.RESET}")
            sys.exit(1)
    except Exception:
        print(f"{C.RED}⚠️  No se pudo conectar a {LLAMA_URL}{C.RESET}")
        print(f"{C.DIM}   Asegúrate de que gemma4-server esté corriendo{C.RESET}")
        sys.exit(1)

    # Load and start MCP
    ecosystem = MCPEcosystem()
    if not ecosystem.load_config():
        sys.exit(1)

    ecosystem.start_all()

    # Create assistant
    assistant = Assistant(ecosystem)

    # Check for direct prompt
    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
        print(f"\n{C.WHITE}[Tú] > {prompt}{C.RESET}")
        response = assistant.chat(prompt)
        print(f"\n{C.GREEN}[IA] > {response}{C.RESET}")
        ecosystem.stop_all()
        return

    # Interactive mode
    print(f"\n{C.DIM}Escribe tu mensaje. Comandos especiales:{C.RESET}")
    print(f"  {C.DIM}/tools      - Ver todas las herramientas{C.RESET}")
    print(f"  {C.DIM}/search <q>  - Buscar herramientas{C.RESET}")
    print(f"  {C.DIM}/clear       - Limpiar historial{C.RESET}")
    print(f"  {C.DIM}/exit        - Salir{C.RESET}\n")

    try:
        while True:
            try:
                user_input = input(f"{C.WHITE}[Tú] > {C.RESET}").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.lower() in ["/exit", "/quit", "/q", "exit", "salir"]:
                break

            if user_input == "/tools":
                print(f"\n{C.CYAN}📋 Herramientas disponibles ({len(ecosystem.all_tools)}):{C.RESET}")
                for name, client in sorted(ecosystem.clients.items()):
                    print(f"\n  {C.YELLOW}[{name}]{C.RESET} ({len(client.tools)} tools):")
                    for tool in client.tools:
                        desc = tool.get("description", "")[:60]
                        print(f"    • {C.GREEN}{tool['name']}{C.RESET}: {C.DIM}{desc}...{C.RESET}")
                continue

            if user_input.startswith("/search "):
                query = user_input[8:].lower()
                print(f"\n{C.CYAN}🔍 Buscando '{query}'...{C.RESET}")
                found = [t for t in ecosystem.all_tools if query in t["name"].lower() or query in t.get("description", "").lower()]
                for tool in found:
                    print(f"  • {C.GREEN}{tool['name']}{C.RESET}: {tool.get('description', '')[:60]}")
                if not found:
                    print(f"  {C.DIM}No se encontraron herramientas{C.RESET}")
                continue

            if user_input == "/clear":
                assistant.messages.clear()
                print(f"{C.DIM}Historial limpiado{C.RESET}")
                continue

            if user_input.startswith("/"):
                print(f"{C.DIM}Comando no reconocido: {user_input}{C.RESET}")
                continue

            # Send to assistant
            print(f"\n{C.GREEN}[IA] > {C.RESET}", end="", flush=True)
            response = assistant.chat(user_input)
            print(response)

    except KeyboardInterrupt:
        print(f"\n\n{C.DIM}Saliendo...{C.RESET}")

    ecosystem.stop_all()
    print(f"{C.GREEN}👋 ¡Hasta luego!{C.RESET}")


if __name__ == "__main__":
    main()
