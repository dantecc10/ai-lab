"""
AI Lab — Telegram Bot LLM Client (llama.cpp OpenAI-Compatible Engine)
Gestiona la comunicación asíncrona con los modelos locales de Gemma 4 y la ejecución de tools.
"""

import os
import json
import httpx
from typing import List, Dict, Any, Tuple
from openai import AsyncOpenAI

from .config import TelegramConfig
from .tools_handler import ToolsHandler


class LLMClient:
    """Cliente asíncrono para llama-server con soporte para Function Calling y Fallback."""

    def __init__(self, config: TelegramConfig, tools_handler: ToolsHandler):
        self.config = config
        self.tools_handler = tools_handler
        self.client = AsyncOpenAI(
            base_url=self.config.llm_url,
            api_key="not-needed-for-local-llama"
        )
        self.active_endpoint = self.config.llm_url
        self.active_model = self.config.model_name
        self.last_usage: Any = None

    def switch_model(self, use_fallback: bool = False):
        """Alterna entre el modelo principal (Gemma 4 12B GPU) y el sub-agente (Gemma 4 E4B CPU)."""
        if use_fallback:
            self.active_endpoint = self.config.fallback_llm_url
            self.active_model = self.config.fallback_model_name
        else:
            self.active_endpoint = self.config.llm_url
            self.active_model = self.config.model_name

        self.client = AsyncOpenAI(
            base_url=self.active_endpoint,
            api_key="not-needed-for-local-llama"
        )

    async def generate_response(self, messages: List[Dict[str, Any]], enable_tools: bool = True) -> str:
        """Genera una respuesta utilizando el LLM local, ejecutando function calling si es necesario."""
        tools = self.tools_handler.get_openai_tools_definition() if (enable_tools and self.config.enable_tools) else None
        
        current_messages = list(messages)
        max_tool_iterations = 4

        for _ in range(max_tool_iterations):
            try:
                kwargs = {
                    "model": self.active_model,
                    "messages": current_messages,
                    "temperature": self.config.temperature,
                    "top_p": self.config.top_p,
                    "max_tokens": self.config.max_tokens,
                }
                if tools:
                    kwargs["tools"] = tools
                    kwargs["tool_choice"] = "auto"

                response = await self.client.chat.completions.create(**kwargs)
                if hasattr(response, "usage") and response.usage:
                    self.last_usage = response.usage

                choice = response.choices[0]
                msg = choice.message

                # Si no hay llamadas a herramientas, retornar respuesta final
                if not msg.tool_calls:
                    content = msg.content
                    if not content and hasattr(msg, "reasoning_content") and msg.reasoning_content:
                        content = msg.reasoning_content
                    return (content or "").strip() or "*(Respuesta vacía del modelo)*"

                # Si el modelo solicitó invocar herramientas:
                # Agregar el mensaje del asistente con las tool_calls
                current_messages.append(msg)

                for tool_call in msg.tool_calls:
                    func_name = tool_call.function.name
                    raw_args = tool_call.function.arguments or "{}"
                    try:
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    except Exception:
                        args = {}

                    # Ejecutar herramienta
                    tool_result = self.tools_handler.execute_function_call(func_name, args)

                    # Añadir respuesta de herramienta a la conversación
                    current_messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": func_name,
                        "content": str(tool_result)
                    })

            except Exception as primary_error:
                # Si falla el endpoint principal, intentar fallback
                if self.active_endpoint != self.config.fallback_llm_url and self.config.fallback_llm_url:
                    print(f"[LLM Main Failed, Trying Fallback]: {primary_error}")
                    try:
                        self.switch_model(use_fallback=True)
                        response = await self.client.chat.completions.create(
                            model=self.active_model,
                            messages=messages,
                            temperature=self.config.temperature,
                            max_tokens=self.config.max_tokens
                        )
                        if hasattr(response, "usage") and response.usage:
                            self.last_usage = response.usage
                        return response.choices[0].message.content or "*(Respuesta de fallback)*"
                    except Exception as fallback_error:
                        return f"⚠️ Error en LLM local: {primary_error}\n(Fallback también falló: {fallback_error})"
                return f"⚠️ Error comunicándose con el modelo local en `{self.active_endpoint}`: {primary_error}"

        return current_messages[-1].get("content", "Completado.")

    async def summarize_for_compaction(self, messages: List[Dict[str, Any]]) -> str:
        """Genera una síntesis estructurada y densa del historial para prolongar la conversación."""
        compact_prompt = [
            {
                "role": "system",
                "content": (
                    "Eres un motor de compactación y síntesis de memoria conversacional. Tu objetivo es resumir "
                    "exhaustivamente el historial previo para preservar el contexto completo en un espacio mínimo de tokens.\n\n"
                    "Debes estructurar el resumen en viñetas densas:\n"
                    "• 🎯 **Objetivos y Estado**: Qué solicitó el usuario, qué se resolvió y qué queda pendiente.\n"
                    "• 📁 **Archivos y Rutas**: Archivos leídos, creados o modificados y su contenido/propósito.\n"
                    "• ⚙️ **Decisiones Técnicas y Comandos**: Arquitectura, variables, puertos, fórmulas o librerías acordadas.\n"
                    "• 💡 **Preferencias del Usuario**: Estilo, notación, idioma o reglas explícitas mencionadas.\n\n"
                    "Sé denso, objetivo, directo y sin texto introductorio innecesario."
                )
            },
            {
                "role": "user",
                "content": f"Compacta el siguiente historial de conversación:\n\n{json.dumps(messages, ensure_ascii=False, indent=1)}"
            }
        ]
        try:
            res = await self.client.chat.completions.create(
                model=self.active_model,
                messages=compact_prompt,
                temperature=0.3,
                max_tokens=2048
            )
            return res.choices[0].message.content or "Historial previo compactado con éxito."
        except Exception as e:
            return f"Historial previo compactado (Error en síntesis automática: {e})"
