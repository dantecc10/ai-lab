"""Chat export, sharing, and R2 storage tools"""

import os
import subprocess
import json
import hashlib
from datetime import datetime
from mcp_common.paths import HOME, safe_path
from mcp_common.logging import log_operation

# ── Constants ────────────────────────────────────────────────
CHAT_SHARE_DIR = os.path.join(HOME, "ai-lab/shared-chats")
CHATSHARE_API_URL = "http://localhost:9095/api/v1"

TOOLS = [
    {
        "name": "chat_export",
        "description": "Guarda y exporta la conversación actual a ChatShare, generando un enlace público de internet en ai.castelancarpinteyro.com.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "messages": {
                    "type": "string",
                    "description": "Mensajes de la conversación en formato JSON: [{\"role\":\"user\",\"content\":\"...\"},...]"
                },
                "title": {
                    "type": "string",
                    "description": "Título descriptivo de la conversación."
                },
                "expires_hours": {
                    "type": "integer",
                    "description": "Horas de validez del enlace (por defecto: 72)."
                }
            },
            "required": ["messages"]
        }
    },
    {
        "name": "chat_share",
        "description": "Genera un enlace público en ai.castelancarpinteyro.com con token de acceso para un chat por su ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": "string",
                    "description": "ID del chat registrado."
                },
                "expires_hours": {
                    "type": "integer",
                    "description": "Horas de validez (por defecto: 72)."
                }
            },
            "required": ["chat_id"]
        }
    },
    {
        "name": "chat_list_shared",
        "description": "Lista los chats guardados en el sistema local de ChatShare.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "chat_get_shared",
        "description": "Obtiene los detalles y mensajes de un chat guardado por su ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "chat_id": {
                    "type": "string",
                    "description": "ID del chat."
                }
            },
            "required": ["chat_id"]
        }
    },
    {
        "name": "r2_upload",
        "description": "Sube un archivo local (imagen, audio, video, documento) a Cloudflare R2 y obtiene su enlace CDN público.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Ruta al archivo local."
                },
                "prefix": {
                    "type": "string",
                    "description": "Carpeta o prefijo en el bucket (por defecto: 'media')."
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "r2_list",
        "description": "Lista los archivos y recursos multimedia alojados en Cloudflare R2.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "prefix": {
                    "type": "string",
                    "description": "Prefijo para filtrar archivos."
                },
                "limit": {
                    "type": "integer",
                    "description": "Límite de resultados (por defecto: 20)."
                }
            }
        }
    },
    {
        "name": "r2_delete",
        "description": "Elimina un archivo de Cloudflare R2 por su clave (key).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "key": {
                    "type": "string",
                    "description": "Clave del archivo en el bucket."
                }
            },
            "required": ["key"]
        }
    },
    {
        "name": "r2_status",
        "description": "Comprueba el estado de conexión y configuración del almacenamiento Cloudflare R2.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "media_view",
        "description": "Muestra un archivo multimedia local (imagen, audio, video) directamente en la ventana del chat web local (:9090 / Open WebUI) sin necesidad de subirlo a internet.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Ruta al archivo local (ej: '~/bitmap.png' o '/home/darkseid/audio.wav')."
                },
                "caption": {
                    "type": "string",
                    "description": "Descripción o título opcional del archivo."
                }
            },
            "required": ["file_path"]
        }
    },
]

def _process_multimedia_in_messages(msgs: list) -> list:
    """Sube archivos multimedia locales detectados en los mensajes a Cloudflare R2 (o fallback Data-URI) para compartirlos en internet."""
    if not isinstance(msgs, list):
        return msgs

    import base64
    import mimetypes
    import re

    try:
        from r2_storage import r2
    except Exception:
        r2 = None

    processed = []
    for m in msgs:
        msg = dict(m)
        content = msg.get("content", "")
        if isinstance(content, str):
            paths = re.findall(r'(/[\w\-./]+\.(?:png|jpg|jpeg|gif|webp|svg|mp3|wav|ogg|m4a|mp4|webm))', content)
            for path in paths:
                if os.path.exists(path) and os.path.isfile(path):
                    file_size = os.path.getsize(path)
                    
                    # 1. Si R2 está disponible y configurado, subir a la CDN
                    if r2 and r2.is_configured:
                        try:
                            upload_res = r2.upload_file(path, prefix="chats")
                            content = content.replace(path, upload_res["url"])
                            continue
                        except Exception as e:
                            log_operation("r2_auto_upload_error", {"path": path}, str(e))

                    # 2. Fallback a Data-URI base64 si el archivo es menor a 15MB
                    if file_size < 15 * 1024 * 1024:
                        mime, _ = mimetypes.guess_type(path)
                        if not mime:
                            mime = "application/octet-stream"
                        try:
                            with open(path, "rb") as f:
                                b64 = base64.b64encode(f.read()).decode("utf-8")
                            data_uri = f"data:{mime};base64,{b64}"
                            content = content.replace(path, data_uri)
                        except Exception:
                            pass
            msg["content"] = content
        processed.append(msg)
    return processed



def _generate_qr_ascii(url: str) -> str:
    """Genera una representación visual en bloques Unicode/ASCII del código QR."""
    try:
        import qrcode
        import io
        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        qr.make(fit=True)
        f = io.StringIO()
        qr.print_ascii(out=f, invert=True)
        f.seek(0)
        return f.read().strip()
    except Exception:
        return ""



# ── Handlers ───────────────────────────────────────────────
def _chat_export_handler(messages: str, title: str = None, expires_hours: int = 72) -> str:
    """Guarda y exporta la conversación completa a ChatShare con soporte multimedia, enlace público en ai.castelancarpinteyro.com y QR visual."""
    try:
        import urllib.request
        import urllib.error
        import urllib.parse

        if isinstance(messages, str):
            try:
                msg_list = json.loads(messages)
            except Exception:
                msg_list = [{"role": "user", "content": messages}]
        elif isinstance(messages, list):
            msg_list = messages
        else:
            return "Error: messages debe ser una lista de mensajes o un string JSON"

        # Procesar archivos multimedia locales
        msg_list = _process_multimedia_in_messages(msg_list)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not title:
            title = f"Chat_{timestamp}"

        # 1. Guardar chat completo en API local
        create_payload = {
            "title": title,
            "messages": msg_list,
            "metadata": {"source": "mcp", "full_verbose": True, "multimedia_enabled": True}
        }
        req = urllib.request.Request(f"{CHATSHARE_API_URL}/chats", method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, data=json.dumps(create_payload).encode("utf-8"), timeout=5) as resp:
            chat_res = json.loads(resp.read().decode("utf-8"))
            chat_id = chat_res["id"]

        # 2. Generar token y enlace público
        share_payload = {
            "expires_hours": expires_hours,
            "label": f"Compartido por IA: {title}"
        }
        req_share = urllib.request.Request(f"{CHATSHARE_API_URL}/chats/{chat_id}/share", method="POST")
        req_share.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req_share, data=json.dumps(share_payload).encode("utf-8"), timeout=5) as resp:
            share_res = json.loads(resp.read().decode("utf-8"))
            share_url = share_res["url"]

        # 3. Guardar copia local de respaldo
        try:
            os.makedirs(CHAT_SHARE_DIR, exist_ok=True)
            json_path = os.path.join(CHAT_SHARE_DIR, f"{chat_id}.json")
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump({"id": chat_id, "title": title, "url": share_url, "messages": msg_list}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

        encoded_url = urllib.parse.quote(share_url, safe="")
        qr_img_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=10&data={encoded_url}"

        log_operation("chat_export", {"title": title}, f"{len(msg_list)} msgs -> {share_url}")
        return (
            f"✅ **Conversación completa guardada y compartida**\n\n"
            f"📝 **Título:** {title}\n"
            f"🌐 **Enlace Público:** [{share_url}]({share_url})\n"
            f"⏱️ **Validez:** {expires_hours} horas (Modo Detallado / Minimal + Multimedia interactiva activa)\n"
            f"💬 **Mensajes incluidos:** {len(msg_list)} (con multimedia, razonamiento y planning completos)\n"
            f"🔑 **ID:** `{chat_id}`\n\n"
            f"### 📱 Escanea para abrir en tu celular:\n"
            f"![Código QR de Acceso]({qr_img_url})"
        )
    except Exception as e:
        return f"Error exportando y compartiendo chat: {e}"



def _chat_share_handler(chat_id: str, expires_hours: int = 72) -> str:
    """Genera un enlace público y QR visual para un chat existente por su ID."""
    try:
        import urllib.request
        import urllib.error
        import urllib.parse

        share_payload = {
            "expires_hours": expires_hours,
            "label": f"Enlace compartido {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        }
        req = urllib.request.Request(f"{CHATSHARE_API_URL}/chats/{chat_id}/share", method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, data=json.dumps(share_payload).encode("utf-8"), timeout=5) as resp:
            share_res = json.loads(resp.read().decode("utf-8"))
            share_url = share_res["url"]

        encoded_url = urllib.parse.quote(share_url, safe="")
        qr_img_url = f"https://api.qrserver.com/v1/create-qr-code/?size=220x220&margin=10&data={encoded_url}"

        log_operation("chat_share", {"chat_id": chat_id}, share_url)
        return (
            f"🔗 **Enlace público generado:**\n"
            f"🌐 [{share_url}]({share_url})\n\n"
            f"⏱️ Válido por {expires_hours} horas.\n\n"
            f"### 📱 Escanea para abrir en tu celular:\n"
            f"![Código QR de Acceso]({qr_img_url})"
        )
    except Exception as e:
        return f"Error generando enlace para el chat {chat_id}: {e}"



def _chat_list_shared_handler() -> str:
    """Lista los chats guardados en ChatShare."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{CHATSHARE_API_URL}/chats?limit=20", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            chats = json.loads(resp.read().decode("utf-8"))

        if not chats:
            return "No hay chats registrados en ChatShare."

        lines = [f"📋 **Chats Registrados ({len(chats)}):**\n"]
        for c in chats:
            lines.append(f"• **{c['title']}** (v{c['version']}) — ID: `{c['id']}`")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listando chats: {e}"



def _chat_get_shared_handler(chat_id: str) -> str:
    """Obtiene los mensajes de un chat por su ID."""
    try:
        import urllib.request
        req = urllib.request.Request(f"{CHATSHARE_API_URL}/chats/{chat_id}", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        lines = [
            f"📝 **{data.get('title', 'Chat')}** (ID: `{data.get('id')}`)",
            f"📅 Creado: {data.get('created_at', '')[:19]}",
            f"💬 Mensajes: {len(data.get('messages', []))}\n"
        ]
        for msg in data.get("messages", []):
            role = "👤 Usuario" if msg.get("role") == "user" else "🤖 Asistente"
            content = msg.get("content", "")[:250]
            lines.append(f"**{role}:** {content}\n")

        return "\n".join(lines)
    except Exception as e:
        return f"Error obteniendo chat {chat_id}: {e}"


# ── Local Media Viewing Tools ─────────────────────────────

def _r2_upload_handler(file_path: str, prefix: str = "media") -> str:
    """Sube un archivo local a Cloudflare R2 y retorna su enlace CDN público."""
    try:
        from r2_storage import r2
        if not r2.is_configured:
            return (
                "⚠️ Cloudflare R2 no está configurado.\n"
                "Para activarlo, guarda tus credenciales en `~/.config/ai-lab/r2.env` o ejecuta en terminal:\n"
                "`r2 configure --account-id ... --access-key ... --secret-key ... --bucket ...`"
            )
        res = r2.upload_file(file_path, prefix=prefix)
        log_operation("r2_upload", {"file": file_path}, res["url"])
        return (
            f"✅ **Archivo subido con éxito a Cloudflare R2**\n\n"
            f"🌐 **URL Pública:** {res['url']}\n"
            f"🔑 **Key:** `{res['key']}`\n"
            f"📦 **Tamaño:** {res['size']} bytes\n"
            f"📄 **Tipo:** `{res['content_type']}`"
        )
    except Exception as e:
        return f"Error subiendo archivo a R2: {e}"



def _r2_list_handler(prefix: str = "", limit: int = 20) -> str:
    """Lista archivos almacenados en Cloudflare R2."""
    try:
        from r2_storage import r2
        if not r2.is_configured:
            return "⚠️ Cloudflare R2 no está configurado."
        items = r2.list_files(prefix=prefix, max_keys=limit)
        if not items:
            return f"No se encontraron archivos en R2 (prefijo: '{prefix}')."

        lines = [f"📂 **Archivos en Cloudflare R2 ({len(items)}):**\n"]
        for it in items:
            size_kb = round(it["size"] / 1024, 1)
            lines.append(f"• **{it['key']}** ({size_kb} KB)\n  🔗 {it['url']}")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listando archivos de R2: {e}"



def _r2_delete_handler(key: str) -> str:
    """Elimina un archivo de Cloudflare R2."""
    try:
        from r2_storage import r2
        if not r2.is_configured:
            return "⚠️ Cloudflare R2 no está configurado."
        r2.delete_file(key)
        log_operation("r2_delete", {"key": key}, "deleted")
        return f"✅ Archivo `{key}` eliminado con éxito de Cloudflare R2."
    except Exception as e:
        return f"Error eliminando archivo de R2: {e}"



def _r2_status_handler() -> str:
    """Comprueba el estado de Cloudflare R2."""
    try:
        from r2_storage import r2
        if not r2.is_configured:
            return (
                "⚠️ Cloudflare R2 no está configurado.\n"
                "Configuración requerida en `~/.config/ai-lab/r2.env`:\n"
                "- R2_ACCOUNT_ID\n- R2_ACCESS_KEY_ID\n- R2_SECRET_ACCESS_KEY\n- R2_BUCKET_NAME\n- R2_PUBLIC_DOMAIN (opcional)"
            )
        items = r2.list_files(max_keys=1)
        dom = f"\n🌐 Dominio CDN: {r2.public_domain}" if r2.public_domain else ""
        return f"🟢 **Cloudflare R2 Conectado y Activo**\n🪣 Bucket: `{r2.bucket_name}`{dom}\n📡 Endpoint S3 Operativo"
    except Exception as e:
        return f"🔴 Error conectando con Cloudflare R2: {e}"


E4B_URL = "http://localhost:9091/v1/chat/completions"
E4B_MODEL = "/home/darkseid/llama.cpp/ai-models/google_gemma-4-E4B-it-Q4_K_M.gguf"



def _media_view_handler(file_path: str, caption: str = "") -> str:
    """Genera el renderizado multimedia para visualizar archivos locales directamente en el chat web de llama (:9090)."""
    try:
        import mimetypes
        import urllib.parse
        from pathlib import Path

        # Expand user path
        if file_path.startswith("~"):
            file_path = os.path.expanduser(file_path)

        p = Path(file_path).resolve()
        if not p.exists():
            return f"❌ Error: El archivo no existe en la ruta: {file_path}"
        if not p.is_file():
            return f"❌ Error: La ruta no es un archivo: {file_path}"

        mime, _ = mimetypes.guess_type(str(p))
        mime = mime or "application/octet-stream"
        ext = p.suffix.lower()
        size_kb = round(p.stat().st_size / 1024, 1)
        name = caption or p.name

        local_url = f"http://localhost:9095/api/v1/media?path={urllib.parse.quote(str(p))}"

        log_operation("media_view", {"path": str(p)}, f"{mime} ({size_kb} KB)")

        # Formatos de imagen
        if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".bmp", ".ico"):
            # Generar Data URI base64 para bypass de COEP y renderizado nativo instantáneo en la UI de llama-server
            if p.stat().st_size < 8 * 1024 * 1024:
                import base64
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                img_src = f"data:{mime};base64,{b64}"
            else:
                img_src = local_url

            return (
                f"🖼️ **Imagen local:** `{p.name}` ({size_kb} KB)\n\n"
                f"![{name}]({img_src})\n\n"
                f"*(Ruta local: `{p}`)*"
            )
        # Formatos de audio
        elif ext in (".mp3", ".wav", ".ogg", ".m4a", ".aac", ".flac", ".opus"):
            if p.stat().st_size < 8 * 1024 * 1024:
                import base64
                with open(p, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("utf-8")
                audio_src = f"data:{mime};base64,{b64}"
            else:
                audio_src = local_url

            return (
                f"🎙️ **Audio local:** `{p.name}` ({size_kb} KB)\n\n"
                f'<audio controls src="{audio_src}" style="width: 100%; margin: 8px 0;"></audio>\n\n'
                f"*(Ruta local: `{p}`)*"
            )
        # Formatos de video
        elif ext in (".mp4", ".webm", ".mov", ".mkv", ".avi"):
            return (
                f"🎥 **Video local:** `{p.name}` ({size_kb} KB)\n\n"
                f'<video controls playsinline src="{local_url}" style="max-width: 100%; max-height: 400px; border-radius: 8px; margin: 8px 0; background: #000;"></video>\n\n'
                f"*(Ruta local: `{p}`)*"
            )
        else:
            return (
                f"📄 **Archivo local disponible:** [{p.name}]({local_url}) ({size_kb} KB)\n"
                f"*(Ruta: `{p}`)*"
            )
    except Exception as e:
        return f"Error preparando visualización de archivo {file_path}: {e}"


# ── Cloudflare R2 Storage Tools ──────────────────────────────

HANDLERS = {
    "chat_export": _chat_export_handler,
    "chat_share": _chat_share_handler,
    "chat_list_shared": _chat_list_shared_handler,
    "chat_get_shared": _chat_get_shared_handler,
    "r2_upload": _r2_upload_handler,
    "r2_list": _r2_list_handler,
    "r2_delete": _r2_delete_handler,
    "r2_status": _r2_status_handler,
    "media_view": _media_view_handler,
}
