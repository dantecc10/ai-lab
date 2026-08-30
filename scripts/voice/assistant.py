import asyncio
import json
import subprocess
import os
import sys
from openai import OpenAI
from kasa_skill import set_plug_state, get_plugs_status

client = OpenAI(
    base_url="http://localhost:9090/v1",
    api_key="not-needed"
)

MODEL_NAME = "/home/darkseid/llama.cpp/ai-models/gemma-4-12b-it-Q4_K_M.gguf"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TTS_SCRIPT = os.path.join(BASE_DIR, "tts_notifier.py")
PYTHON_BIN = sys.executable

tools = [
    {
        "type": "function",
        "function": {
            "name": "set_plug_state",
            "description": "Enciende o apaga uno o todos los enchufes inteligentes (ElektroDante, Lux, o 'todos').",
            "parameters": {
                "type": "object",
                "properties": {
                    "device_name": {
                        "type": "string",
                        "description": "Nombre del dispositivo ('ElektroDante', 'Lux', 'luz', o 'todos')."
                    },
                    "turn_on": {
                        "type": "boolean",
                        "description": "True para encender, False para apagar."
                    }
                },
                "required": ["device_name", "turn_on"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_plugs_status",
            "description": "Obtiene el estado actual (encendido/apagado) de todos los enchufes.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    }
]

def trigger_voice_response(text: str):
    """Lanza el TTS y la notificación de escritorio en segundo plano."""
    subprocess.Popen([PYTHON_BIN, TTS_SCRIPT, text])

async def run_conversation(user_prompt: str) -> str:
    messages = [
        {
            "role": "system",
            "content": (
                "Eres un asistente domótico local en Pop!_OS. Tienes control directo sobre dos enchufes Kasa: "
                "'ElektroDante' y 'Lux'. Emplea las herramientas provistas para modificar o consultar su estado. "
                "Sé conciso y claro en tus respuestas."
            )
        },
        {"role": "user", "content": user_prompt}
    ]

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=messages,
        tools=tools,
        tool_choice="auto"
    )

    msg = response.choices[0].message

    if msg.tool_calls:
        messages.append(msg)
        for tool_call in msg.tool_calls:
            fn_name = tool_call.function.name
            args = json.loads(tool_call.function.arguments or "{}")

            if fn_name == "set_plug_state":
                tool_output = await set_plug_state(args["device_name"], args["turn_on"])
            elif fn_name == "get_plugs_status":
                tool_output = await get_plugs_status()
            else:
                tool_output = "Herramienta desconocida."

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": tool_output
            })

        final_response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages
        )
        bot_reply = final_response.choices[0].message.content
    else:
        bot_reply = msg.content

    print(f"\n[Gemma]: {bot_reply}")
    trigger_voice_response(bot_reply)
    return bot_reply

if __name__ == "__main__":
    while True:
        try:
            cmd = input("\n[Tú] > ")
            if cmd.strip().lower() in ["exit", "salir", "q"]:
                break
            if cmd.strip():
                asyncio.run(run_conversation(cmd))
        except KeyboardInterrupt:
            break
