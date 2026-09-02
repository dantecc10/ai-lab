#!/usr/bin/env python3
"""
Chat Export & Share System
Export conversations from llama.cpp and share via web server with QR codes.
"""

import os
import sys
import json
import secrets
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# Add venv site-packages
skills_venv = os.path.expanduser("~/scripting/gpu-tools/skills/.venv/lib/python3.12/site-packages")
if os.path.exists(skills_venv) and skills_venv not in sys.path:
    sys.path.insert(0, skills_venv)

import qrcode

# Configuration
HOST = "0.0.0.0"
PORT = 9094
SHARED_DIR = os.path.expanduser("~/ai-lab/shared-chats")
BASE_URL = f"http://localhost:{PORT}"

os.makedirs(SHARED_DIR, exist_ok=True)


def generate_id():
    return secrets.token_urlsafe(8)


def export_chat(messages, title=None):
    chat_id = generate_id()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if not title:
        title = f"Chat_{timestamp}"

    chat_data = {
        "id": chat_id,
        "title": title,
        "created_at": datetime.now().isoformat(),
        "messages": messages
    }

    # Save JSON
    json_path = os.path.join(SHARED_DIR, f"{chat_id}.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(chat_data, f, ensure_ascii=False, indent=2)

    # Save Markdown
    md_path = os.path.join(SHARED_DIR, f"{chat_id}.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n\n")
        f.write(f"*Exportado: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}*\n\n---\n\n")
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            if role == "user":
                f.write(f"## Usuario\n\n{content}\n\n")
            elif role == "assistant":
                f.write(f"## Asistente\n\n{content}\n\n")
            f.write("---\n\n")

    share_url = f"{BASE_URL}/chat/{chat_id}"

    # Generate QR
    qr_path = os.path.join(SHARED_DIR, f"{chat_id}_qr.png")
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(share_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img.save(qr_path)

    return {
        "id": chat_id,
        "title": title,
        "json_path": json_path,
        "md_path": md_path,
        "qr_path": qr_path,
        "share_url": share_url,
        "messages_count": len(messages)
    }


def list_shared_chats():
    chats = []
    for filename in os.listdir(SHARED_DIR):
        if filename.endswith(".json"):
            filepath = os.path.join(SHARED_DIR, filename)
            try:
                with open(filepath) as f:
                    data = json.load(f)
                chats.append({
                    "id": data.get("id"),
                    "title": data.get("title"),
                    "created_at": data.get("created_at"),
                    "messages_count": len(data.get("messages", []))
                })
            except:
                pass
    return sorted(chats, key=lambda x: x.get("created_at", ""), reverse=True)


def get_chat(chat_id):
    filepath = os.path.join(SHARED_DIR, f"{chat_id}.json")
    if not os.path.exists(filepath):
        return None
    with open(filepath) as f:
        return json.load(f)


def render_chat_html(chat, chat_id):
    title = chat.get("title", "Chat")
    created_at = chat.get("created_at", "")[:19]
    messages_count = len(chat.get("messages", []))

    messages_html = ""
    for msg in chat.get("messages", []):
        role = msg.get("role", "unknown")
        content = msg.get("content", "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        role_class = "user" if role == "user" else "assistant"
        role_label = "Usuario" if role == "user" else "Asistente"
        icon = "👤" if role == "user" else "🤖"
        messages_html += f'<div class="message {role_class}"><div class="role">{icon} {role_label}</div><div class="content">{content}</div></div>\n'

    share_url = f"{BASE_URL}/chat/{chat_id}"

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; line-height: 1.6; padding: 20px; }}
.container {{ max-width: 800px; margin: 0 auto; }}
h1 {{ text-align: center; margin-bottom: 10px; color: #00d4ff; }}
.meta {{ text-align: center; color: #888; margin-bottom: 30px; font-size: 0.9em; }}
.message {{ background: #16213e; border-radius: 12px; padding: 16px; margin-bottom: 16px; border-left: 4px solid #0f3460; }}
.message.user {{ border-left-color: #00d4ff; background: #1a1a3e; }}
.message.assistant {{ border-left-color: #00ff88; }}
.role {{ font-weight: bold; margin-bottom: 8px; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; }}
.message.user .role {{ color: #00d4ff; }}
.message.assistant .role {{ color: #00ff88; }}
.content {{ white-space: pre-wrap; }}
.qr-section {{ text-align: center; margin-top: 40px; padding: 20px; background: #16213e; border-radius: 12px; }}
.qr-section img {{ max-width: 200px; margin: 10px; }}
.share-url {{ word-break: break-all; color: #00d4ff; font-family: monospace; font-size: 0.9em; }}
</style>
</head>
<body>
<div class="container">
<h1>{title}</h1>
<div class="meta">Exportado: {created_at} | {messages_count} mensajes</div>
{messages_html}
<div class="qr-section">
<h3>Compartir este chat</h3>
<img src="/qr/{chat_id}" alt="QR Code">
<p class="share-url">{share_url}</p>
</div>
</div>
</body>
</html>"""


def render_list_html(chats):
    items = ""
    for chat in chats:
        items += f'<div class="message"><a href="/chat/{chat["id"]}" style="color: #00d4ff; text-decoration: none;"><div class="role">📝 {chat["title"]}</div></a><div class="content">{chat["messages_count"]} mensajes | {chat["created_at"][:10]}</div></div>\n'

    if not items:
        items = '<div class="message"><div class="content">No hay chats compartidos aun</div></div>'

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Chats Compartidos</title>
<style>
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #1a1a2e; color: #eee; line-height: 1.6; padding: 20px; }}
.container {{ max-width: 800px; margin: 0 auto; }}
h1 {{ text-align: center; margin-bottom: 20px; color: #00d4ff; }}
.message {{ background: #16213e; border-radius: 12px; padding: 16px; margin-bottom: 16px; border-left: 4px solid #0f3460; }}
.role {{ font-weight: bold; margin-bottom: 8px; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; }}
.content {{ color: #888; font-size: 0.9em; }}
</style>
</head>
<body>
<div class="container">
<h1>Chats Compartidos</h1>
{items}
</div>
</body>
</html>"""


class ChatShareHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/":
            self.send_list_page()
        elif parsed.path.startswith("/chat/"):
            chat_id = parsed.path.split("/chat/")[1]
            self.send_chat_page(chat_id)
        elif parsed.path.startswith("/qr/"):
            chat_id = parsed.path.split("/qr/")[1]
            self.send_qr(chat_id)
        elif parsed.path == "/api/chats":
            self.send_json(list_shared_chats())
        elif parsed.path.startswith("/api/chat/"):
            chat_id = parsed.path.split("/api/chat/")[1]
            chat = get_chat(chat_id)
            if chat:
                self.send_json(chat)
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/export":
            self.handle_export()
        else:
            self.send_error(404)

    def send_list_page(self):
        chats = list_shared_chats()
        html = render_list_html(chats)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def send_chat_page(self, chat_id):
        chat = get_chat(chat_id)
        if not chat:
            self.send_error(404)
            return
        html = render_chat_html(chat, chat_id)
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def send_qr(self, chat_id):
        qr_path = os.path.join(SHARED_DIR, f"{chat_id}_qr.png")
        if not os.path.exists(qr_path):
            share_url = f"{BASE_URL}/chat/{chat_id}"
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(share_url)
            qr.make(fit=True)
            img = qr.make_image(fill_color="black", back_color="white")
            img.save(qr_path)

        with open(qr_path, "rb") as f:
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.end_headers()
            self.wfile.write(f.read())

    def send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def handle_export(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        try:
            data = json.loads(body)
            messages = data.get("messages", [])
            title = data.get("title", None)
            result = export_chat(messages, title)
            self.send_json(result)
        except Exception as e:
            self.send_json({"error": str(e)})

    def log_message(self, format, *args):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {format % args}")


def main():
    print(f"Chat Share Server running on {BASE_URL}")
    print(f"Shared chats: {SHARED_DIR}")
    server = HTTPServer((HOST, PORT), ChatShareHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        server.shutdown()


if __name__ == "__main__":
    main()
