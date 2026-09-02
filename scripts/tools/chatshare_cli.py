#!/usr/bin/env python3
"""
ChatShare CLI — Herramienta de línea de comandos para gestionar y compartir chats.
"""

import sys
import os
import json
import argparse
import urllib.request
import urllib.error

API_BASE = "http://localhost:9095/api/v1"


def _api_call(method: str, endpoint: str, data: dict = None) -> dict:
    url = f"{API_BASE}{endpoint}"
    req = urllib.request.Request(url, method=method)
    req.add_header("Content-Type", "application/json")
    body = json.dumps(data).encode("utf-8") if data else None

    try:
        with urllib.request.urlopen(req, data=body, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"❌ Error conectando con ChatShare local en {API_BASE}: {e}", file=sys.stderr)
        print("💡 Asegúrate de que el servicio esté corriendo: systemctl --user status chatmanager.service", file=sys.stderr)
        sys.exit(1)


def cmd_list(args):
    chats = _api_call("GET", f"/chats?limit={args.limit}")
    if not chats:
        print("ℹ️ No hay chats registrados aún.")
        return

    print("\n📂 Chats Registrados en AI Lab:")
    print("─" * 70)
    print(f"{'ID':<38} {'Versión':<8} {'Título'}")
    print("─" * 70)
    for c in chats:
        print(f"{c['id']:<38} v{c['version']:<7} {c['title']}")
    print("─" * 70)
    print(f"Total: {len(chats)} chats\n")


def cmd_share(args):
    payload = {
        "expires_hours": args.hours,
        "label": args.label,
        "max_views": args.max_views
    }
    res = _api_call("POST", f"/chats/{args.chat_id}/share", payload)
    
    print("\n🔗 ¡Enlace Público de ChatShare Generado con Éxito!")
    print("─" * 70)
    print(f"🌐 URL:        {res['url']}")
    print(f"⏱️ Expira en:  {args.hours} horas ({res.get('expires_at', '')[:19]})")
    if args.label:
        print(f"🏷️ Etiqueta:   {args.label}")
    print("─" * 70)
    print("ℹ️ Sincronizado automáticamente con ai.castelancarpinteyro.com\n")


def cmd_create(args):
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            messages = json.load(f)
    except Exception as e:
        print(f"❌ Error leyendo archivo JSON: {e}", file=sys.stderr)
        sys.exit(1)

    payload = {
        "title": args.title,
        "messages": messages,
        "metadata": {"source": "cli"}
    }
    chat = _api_call("POST", "/chats", payload)
    print(f"✅ Chat creado con ID: {chat['id']}")

    if args.share:
        args.chat_id = chat["id"]
        args.hours = 72
        args.label = "Compartido desde CLI"
        args.max_views = None
        cmd_share(args)


def cmd_status(args):
    try:
        req = urllib.request.Request("http://localhost:9095/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "ok":
                print("🟢 Servicio Local ChatShare (puerto 9095): Activo y Saludable")
            else:
                print(f"🟡 Servicio Local ChatShare: Respuesta inesperada {data}")
    except Exception as e:
        print(f"🔴 Servicio Local ChatShare: Inactivo ({e})")

    try:
        req = urllib.request.Request("https://ai.castelancarpinteyro.com/health")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("status") == "ok":
                print("🟢 VPS Público (ai.castelancarpinteyro.com): Activo y Conectado")
            else:
                print(f"🟡 VPS Público: Respuesta inesperada {data}")
    except Exception as e:
        print(f"🔴 VPS Público (ai.castelancarpinteyro.com): Error de conexión ({e})")


def main():
    parser = argparse.ArgumentParser(description="ChatShare CLI — Gestionar y compartir chats en internet")
    subparsers = parser.add_subparsers(dest="subcommand", help="Comando a ejecutar")

    # List
    p_list = subparsers.add_parser("list", help="Listar chats locales")
    p_list.add_argument("--limit", type=int, default=20, help="Límite de resultados")

    # Share
    p_share = subparsers.add_parser("share", help="Generar enlace público de internet para un chat")
    p_share.add_argument("chat_id", help="ID del chat a compartir")
    p_share.add_argument("--hours", type=int, default=72, help="Horas de validez del enlace (default: 72)")
    p_share.add_argument("--label", type=str, default="", help="Etiqueta opcional para el enlace")
    p_share.add_argument("--max-views", type=int, default=None, help="Límite máximo de visualizaciones")

    # Create
    p_create = subparsers.add_parser("create", help="Crear nuevo chat desde un archivo JSON con mensajes")
    p_create.add_argument("title", help="Título del chat")
    p_create.add_argument("file", help="Ruta al archivo JSON con la lista de mensajes")
    p_create.add_argument("--share", action="store_true", help="Generar enlace público inmediatamente")

    # Status
    subparsers.add_parser("status", help="Comprobar estado del servicio local y VPS")

    args = parser.parse_args()
    if not args.subcommand:
        parser.print_help()
        sys.exit(0)

    if args.subcommand == "list":
        cmd_list(args)
    elif args.subcommand == "share":
        cmd_share(args)
    elif args.subcommand == "create":
        cmd_create(args)
    elif args.subcommand == "status":
        cmd_status(args)


if __name__ == "__main__":
    main()
