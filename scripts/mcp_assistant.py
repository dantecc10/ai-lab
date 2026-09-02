#!/usr/bin/env python3
"""
AI Lab — Asistente de Terminal MCP Avanzado con Motor ReAct y Guardrails de Seguridad
Uso:
     python3 mcp_assistant.py [prompt]
     python3 mcp_assistant.py                 # modo interactivo con guardrails
     python3 mcp_assistant.py --auto [prompt] # modo ejecución autónoma
     python3 mcp_assistant.py --safe-mode     # bloqueo estricto de herramientas críticas
"""

import os
import sys
import json
import time
import argparse
import subprocess
import signal
from pathlib import Path

# Inyectar venv de herramientas si existe
skills_venv = os.path.expanduser("~/scripting/gpu-tools/skills/.venv/lib/python3.12/site-packages")
if os.path.exists(skills_venv) and skills_venv not in sys.path:
    sys.path.insert(0, skills_venv)

ai_lab_root = str(Path(__file__).resolve().parent.parent)
if ai_lab_root not in sys.path:
    sys.path.insert(0, ai_lab_root)

from openai import OpenAI

# ── Importaciones de AI Lab Core ───────────────────────────────
try:
    from scripts.tools.security_guard import SecurityGuard
    from scripts.tools.audit_logger import AuditLogger
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.tools.security_guard import SecurityGuard
    from scripts.tools.audit_logger import AuditLogger

# ── Configuración ────────────────────────────────────────────
LLAMA_URL = os.environ.get("LLAMA_URL", "http://localhost:9090")
MODEL = os.environ.get("MODEL", "/home/darkseid/llama.cpp/ai-models/gemma-4-12b-it-Q4_K_M.gguf")
MCP_CONFIG = Path.home() / ".config" / "mcp-servers.json"
SKILLS_DIR = Path.home() / "scripting/gpu-tools/skills"

# ── Colores y Formato ────────────────────────────────────────
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
    BG_RED = "\033[41m"
    BG_YELLOW = "\033[43m"


def banner():
    print(f"""{C.CYAN}{C.BOLD}
╔═══════════════════════════════════════════════════════════════════╗
║         🤖 AI Lab — MCP Autonomous & Guarded Assistant            ║
║     llama.cpp + ReAct Auto-Correction + Security Guardrails       ║
╚═══════════════════════════════════════════════════════════════════╝{C.RESET}
""")


# ── MCP Client ───────────────────────────────────────────────
class MCPClient:
    """Cliente para comunicarse con un MCP server vía JSON-RPC sobre stdio."""

    def __init__(self, name: str, command: list[str]):
        self.name = name
        self.command = command
        self.process = None
        self.tools = []
        self._request_id = 0

    def start(self) -> bool:
        """Inicia el MCP server como subproceso."""
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=str(SKILLS_DIR) if SKILLS_DIR.exists() else None,
                env={**os.environ, "PYTHONUNBUFFERED": "1"}
            )

            # Handshake Initialize
            response = self._send("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ai-lab-assistant", "version": "2.0.0"}
            })

            if not response:
                return False

            self._notify("notifications/initialized", {})

            # Obtener listado de tools
            tools_response = self._send("tools/list", {})
            if tools_response and "tools" in tools_response:
                self.tools = tools_response["tools"]

            return True

        except Exception as e:
            print(f"{C.RED}Error al iniciar MCP server '{self.name}': {e}{C.RESET}")
            return False

    def _send(self, method: str, params: dict) -> dict | None:
        """Envía petición JSON-RPC y espera respuesta."""
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
        """Envía notificación JSON-RPC sin esperar respuesta."""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        try:
            self.process.stdin.write(json.dumps(notification) + "\n")
            self.process.stdin.flush()
        except Exception:
            pass

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Ejecuta una herramienta en el servidor MCP."""
        response = self._send("tools/call", {
            "name": tool_name,
            "arguments": arguments
        })

        if not response:
            return f"Error: Sin respuesta del servidor MCP {self.name}"

        if "error" in response:
            return f"Error: {response['error']}"

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
        """Finaliza el subproceso del servidor MCP."""
        if self.process:
            try:
                self.process.stdin.close()
                self.process.terminate()
                self.process.wait(timeout=3)
            except Exception:
                try:
                    self.process.kill()
                except Exception:
                    pass


# ── Ecosistema MCP ──────────────────────────────────────────
class MCPEcosystem:
    """Orquestador de múltiples servidores MCP y catálogo unificado de tools."""

    def __init__(self):
        self.clients: dict[str, MCPClient] = {}
        self.all_tools: list[dict] = []
        self.tool_map: dict[str, MCPClient] = {}

    def load_config(self) -> bool:
        if not MCP_CONFIG.exists():
            print(f"{C.RED}No se encontró configuración en {MCP_CONFIG}{C.RESET}")
            return False

        with open(MCP_CONFIG, "r", encoding="utf-8") as f:
            config = json.load(f)

        servers = config.get("mcpServers", {})
        if not servers:
            print(f"{C.RED}No hay servidores MCP configurados en {MCP_CONFIG}{C.RESET}")
            return False

        for name, server_config in servers.items():
            command = server_config.get("command", "")
            args = server_config.get("args", [])
            if not command:
                continue
            full_command = [command] + args
            self.clients[name] = MCPClient(name, full_command)

        return True

    def start_all(self):
        print(f"\n{C.YELLOW}Iniciando servidores MCP...{C.RESET}")
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

        print(f"\n{C.GREEN}{C.BOLD}✅ Total: {len(self.all_tools)} herramientas operativas{C.RESET}")

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        client = self.tool_map.get(tool_name)
        if not client:
            return f"Error: Tool '{tool_name}' no encontrada en ningún servidor MCP activo."
        return client.call_tool(tool_name, arguments)

    def get_openai_tools(self) -> list[dict]:
        openai_tools = []
        for tool in self.all_tools:
            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool.get("inputSchema", {"type": "object", "properties": {}})
                }
            })
        return openai_tools

    def stop_all(self):
        for client in self.clients.values():
            client.stop()


# ── Asistente con Motor ReAct y Guardrails ──────────────────
class Assistant:
    """Asistente de IA local con supervisión de seguridad, métricas y bucle ReAct."""

    def __init__(
        self,
        ecosystem: MCPEcosystem,
        auto_mode: bool = False,
        safe_mode: bool = False
    ):
        self.eco = ecosystem
        self.auto_mode = auto_mode
        self.safe_mode = safe_mode
        self.client = OpenAI(base_url=f"{LLAMA_URL}/v1", api_key="not-needed")
        self.messages = []
        self.guard = SecurityGuard()
        self.audit = AuditLogger()
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        prompt_file = Path.home() / ".config" / "system-prompt.txt"
        if prompt_file.exists():
            return prompt_file.read_text(encoding="utf-8").strip()

        return (
            "Eres el Asistente de IA de AI Lab en Pop!_OS con aceleración GPU NVIDIA y 148+ herramientas MCP. "
            "Operas con un bucle de ejecución autónoma (ReAct). Cuando una herramienta o comando devuelva un error, "
            "reflexiona sobre la causa raíz, formula una hipótesis correctiva y ajusta los parámetros antes de continuar. "
            "Prioriza la seguridad, la precisión técnica y respuestas concisas."
        )

    def _format_risk_badge(self, risk: str) -> str:
        if risk == "safe":
            return f"{C.GREEN}[SAFE]{C.RESET}"
        elif risk == "medium":
            return f"{C.YELLOW}[MEDIUM]{C.RESET}"
        elif risk == "high_risk":
            return f"{C.RED}{C.BOLD}[HIGH RISK]{C.RESET}"
        return f"{C.MAGENTA}[{risk.upper()}]{C.RESET}"

    def chat(self, user_message: str, max_steps: int = 15) -> str:
        """Ejecuta el bucle ReAct de planificación, tool calls y auto-corrección."""
        self.messages.append({"role": "user", "content": user_message})
        tools = self.eco.get_openai_tools()[:140]

        # Enriquecer prompt con directivas aprendidas y entidades mencionadas (JIT)
        dynamic_system_prompt = self.system_prompt
        try:
            from scripts.tools.knowledge_graph import KnowledgeGraphEngine
            kg = KnowledgeGraphEngine()
            jit_context = kg.format_jit_context_block(user_message)
            if jit_context:
                dynamic_system_prompt += f"\n\n{jit_context}"
        except Exception:
            pass

        # Context Compaction para mantener coherencia en conversaciones largas
        try:
            from scripts.tools.context_compactor import ContextCompactor
            compactor = ContextCompactor()
            if len(self.messages) > 10:
                compact_res = compactor.compact_conversation(self.messages, max_recent=8)
                history_payload = compact_res["assembled_messages"]
            else:
                history_payload = self.messages
        except Exception:
            history_payload = self.messages[-20:]

        for step in range(1, max_steps + 1):
            try:
                response = self.client.chat.completions.create(
                    model=MODEL,
                    messages=[
                        {"role": "system", "content": dynamic_system_prompt}
                    ] + history_payload,
                    tools=tools,
                    tool_choice="auto",
                    temperature=0.7
                )
            except Exception as e:
                return f"{C.RED}Error en inferencia LLM ({LLAMA_URL}): {e}{C.RESET}"

            msg = response.choices[0].message

            if not msg.tool_calls:
                self.messages.append({"role": "assistant", "content": msg.content or ""})
                return msg.content or "(Respuesta vacía)"

            # Registrar tool calls en historial
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

            # Procesar cada tool call
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                try:
                    args = json.loads(tool_call.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                risk_level = self.guard.get_risk_level(fn_name)
                badge = self._format_risk_badge(risk_level)

                # Argumentos resumidos para visualización
                args_preview = ", ".join(f"{k}={repr(v)[:40]}" for k, v in args.items())
                print(f"  {badge} {C.CYAN}🔧 Paso {step}/{max_steps} → {fn_name}({args_preview}){C.RESET}", file=sys.stderr)

                # Evaluación de Guardrails de Seguridad
                eval_res = self.guard.evaluate_execution(fn_name, args, user_confirmed=self.auto_mode)
                
                # Caso: Bloqueo de seguridad estricto
                if not eval_res["allowed"] and eval_res["risk"] == "blocked":
                    print(f"  {C.RED}⛔ BLOQUEADO: {eval_res['reason']}{C.RESET}", file=sys.stderr)
                    tool_output = f"🛡️ Bloqueo de Seguridad Crítico: {eval_res['reason']}. La operación fue rechazada por contener patrones destructivos."
                    self.messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": tool_output
                    })
                    continue

                # Caso: Requiere confirmación interactiva
                if eval_res["requires_confirmation"] and not self.auto_mode:
                    if self.safe_mode:
                        print(f"  {C.RED}🛑 SAFE-MODE: Ejecución de '{fn_name}' cancelada por política de solo lectura.{C.RESET}", file=sys.stderr)
                        tool_output = f"Acción '{fn_name}' denegada debido al modo seguro (--safe-mode)."
                    else:
                        print(f"\n  {C.YELLOW}{C.BOLD}⚠️  CONFIRMACIÓN DE SEGURIDAD{C.RESET}")
                        print(f"  {C.DIM}Herramienta de alto riesgo:{C.RESET} {C.WHITE}{fn_name}{C.RESET}")
                        print(f"  {C.DIM}Argumentos:{C.RESET} {json.dumps(args, indent=2)}")
                        try:
                            confirm = input(f"  {C.YELLOW}¿Autorizar ejecución? [s/N]: {C.RESET}").strip().lower()
                        except (EOFError, KeyboardInterrupt):
                            confirm = "n"

                        if confirm not in ["s", "si", "y", "yes"]:
                            print(f"  {C.RED}❌ Acción cancelada por el usuario.{C.RESET}\n", file=sys.stderr)
                            tool_output = f"Operación '{fn_name}' cancelada manualmente por el usuario."
                        else:
                            # Ejecución autorizada
                            t0 = time.time()
                            tool_output = self.eco.call_tool(fn_name, args)
                            dur_ms = (time.time() - t0) * 1000.0
                            print(f"  {C.GREEN}✓ Completado ({dur_ms:.1f}ms){C.RESET}", file=sys.stderr)
                else:
                    # Ejecución directa autorizada
                    t0 = time.time()
                    tool_output = self.eco.call_tool(fn_name, args)
                    dur_ms = (time.time() - t0) * 1000.0
                    print(f"  {C.DIM}↳ Ejecutado en {dur_ms:.1f}ms{C.RESET}", file=sys.stderr)

                # Detección de error y mensaje de auto-reflexión ReAct
                is_error = "Error" in tool_output or "Bloqueo de Seguridad" in tool_output
                if is_error and step < max_steps:
                    print(f"  {C.MAGENTA}🔄 [ReAct Auto-Corrección activada]{C.RESET}", file=sys.stderr)

                # Truncar respuestas masivas
                if len(tool_output) > 8000:
                    tool_output = tool_output[:8000] + "\n... [salida truncada para proteger contexto]"

                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": tool_output
                })

        return "Se alcanzó el límite máximo de pasos de auto-corrección ReAct."


# ── Función Principal y CLI ──────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="AI Lab — Asistente de Terminal MCP Avanzado con Guardrails y ReAct"
    )
    parser.add_argument("prompt", nargs="*", help="Prompt directo a ejecutar")
    parser.add_argument("--auto", "--no-confirm", action="store_true", help="Modo autónomo (omite confirmación en tools de alto riesgo)")
    parser.add_argument("--safe-mode", action="store_true", help="Bloquea terminantemente herramientas de alto riesgo")
    parser.add_argument("--max-steps", type=int, default=15, help="Máximo de iteraciones ReAct (default: 15)")
    args = parser.parse_args()

    banner()

    # Comprobar salud de llama-server
    try:
        import urllib.request
        req = urllib.request.Request(f"{LLAMA_URL}/health")
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status != 200:
                print(f"{C.RED}⚠️ llama-server no responde adecuadamente en {LLAMA_URL}{C.RESET}")
    except Exception:
        print(f"{C.RED}⚠️ No se pudo conectar a {LLAMA_URL}. Asegúrate de que gemma4-server.service esté activo.{C.RESET}")
        sys.exit(1)

    # Iniciar ecosistema MCP
    ecosystem = MCPEcosystem()
    if not ecosystem.load_config():
        sys.exit(1)

    ecosystem.start_all()

    # Crear asistente
    assistant = Assistant(
        ecosystem=ecosystem,
        auto_mode=args.auto,
        safe_mode=args.safe_mode
    )

    # Modo prompt directo
    if args.prompt:
        prompt_text = " ".join(args.prompt)
        print(f"\n{C.WHITE}{C.BOLD}[Tú] > {prompt_text}{C.RESET}\n")
        response = assistant.chat(prompt_text, max_steps=args.max_steps)
        print(f"\n{C.GREEN}{C.BOLD}[IA] > {C.RESET}{response}")
        ecosystem.stop_all()
        return

    # Modo interactivo
    print(f"\n{C.DIM}Comandos especiales disponibles:{C.RESET}")
    print(f"  {C.CYAN}/metrics{C.RESET}    — Ver métricas agregadas de rendimiento y GPU")
    print(f"  {C.CYAN}/traces{C.RESET}     — Ver últimas trazas de ejecución de herramientas")
    print(f"  {C.CYAN}/policy{C.RESET}     — Consultar estado de políticas y guardrails")
    print(f"  {C.CYAN}/tools{C.RESET}      — Listar todas las herramientas cargadas")
    print(f"  {C.CYAN}/search <q>{C.RESET} — Buscar herramientas por palabra clave")
    print(f"  {C.CYAN}/clear{C.RESET}      — Limpiar historial de conversación")
    print(f"  {C.CYAN}/exit{C.RESET}       — Finalizar sesión\n")

    try:
        while True:
            try:
                user_input = input(f"{C.WHITE}{C.BOLD}[Tú] > {C.RESET}").strip()
            except EOFError:
                break

            if not user_input:
                continue

            if user_input.lower() in ["/exit", "/quit", "/q", "exit", "salir"]:
                break

            if user_input == "/metrics":
                print(assistant.audit.get_metrics(24))
                continue

            if user_input == "/traces":
                traces = assistant.audit.list_recent_traces(10)
                print(f"\n{C.CYAN}📜 Trazas Recientes:{C.RESET}")
                for t in traces:
                    icon = "✅" if t["success"] else "❌"
                    print(f"  {icon} [#{t['id']} {t['timestamp']}] {t['tool']} — {t['duration_ms']}ms (VRAM: {t['vram_mb']}MB)")
                continue

            if user_input == "/policy":
                print(f"\n{C.CYAN}🛡️ Políticas de Seguridad Activas:{C.RESET}")
                print(f"  • Modo: {assistant.guard.security_mode}")
                print(f"  • Confirmación High-Risk: {assistant.guard.require_confirmation_high_risk}")
                print(f"  • Bloqueo destructivo: {assistant.guard.block_dangerous_patterns}")
                print(f"  • Tools: Safe={len(assistant.guard.safe_tools)} | Medium={len(assistant.guard.medium_tools)} | High-Risk={len(assistant.guard.high_risk_tools)}")
                continue

            if user_input == "/tools":
                print(f"\n{C.CYAN}📋 Herramientas Disponibles ({len(ecosystem.all_tools)}):{C.RESET}")
                for name, client in sorted(ecosystem.clients.items()):
                    print(f"\n  {C.YELLOW}[{name}]{C.RESET} ({len(client.tools)} tools):")
                    for tool in client.tools:
                        risk = assistant.guard.get_risk_level(tool["name"])
                        badge = assistant._format_risk_badge(risk)
                        desc = tool.get("description", "")[:60]
                        print(f"    {badge} {C.GREEN}{tool['name']}{C.RESET}: {C.DIM}{desc}...{C.RESET}")
                continue

            if user_input.startswith("/search "):
                query = user_input[8:].lower()
                print(f"\n{C.CYAN}🔍 Buscando '{query}'...{C.RESET}")
                found = [t for t in ecosystem.all_tools if query in t["name"].lower() or query in t.get("description", "").lower()]
                for tool in found:
                    risk = assistant.guard.get_risk_level(tool["name"])
                    badge = assistant._format_risk_badge(risk)
                    print(f"  {badge} {C.GREEN}{tool['name']}{C.RESET}: {tool.get('description', '')[:70]}")
                if not found:
                    print(f"  {C.DIM}No se encontraron herramientas que coincidan con '{query}'{C.RESET}")
                continue

            if user_input == "/clear":
                assistant.messages.clear()
                print(f"{C.DIM}Historial de conversación reiniciado.{C.RESET}")
                continue

            if user_input.startswith("/"):
                print(f"{C.DIM}Comando no reconocido: {user_input}{C.RESET}")
                continue

            print(f"\n{C.GREEN}{C.BOLD}[IA] > {C.RESET}", end="", flush=True)
            response = assistant.chat(user_input, max_steps=args.max_steps)
            print(response + "\n")

    except KeyboardInterrupt:
        print(f"\n\n{C.DIM}Sesión interrumpida.{C.RESET}")

    ecosystem.stop_all()
    print(f"{C.GREEN}👋 Sesión finalizada.{C.RESET}")


if __name__ == "__main__":
    main()
