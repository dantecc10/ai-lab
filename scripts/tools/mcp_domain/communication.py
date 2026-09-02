"""Notification, WhatsApp, email, and reminder tools"""

import os
import subprocess
import json
import socket

from urllib.parse import quote
from mcp_common.paths import HOME
from mcp_common.logging import log_operation
from mcp_common.crypto import encrypt_value

TOOLS = [
    {
        "name": "send_notification",
        "description": "Envía una notificación de escritorio con opciones avanzadas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Título de la notificación."
                },
                "message": {
                    "type": "string",
                    "description": "Mensaje de la notificación."
                },
                "urgency": {
                    "type": "string",
                    "enum": ["low", "normal", "critical"],
                    "description": "Nivel de urgencia.",
                    "default": "normal"
                },
                "icon": {
                    "type": "string",
                    "description": "Ruta del icono o nombre stock (ej: dialog-information, weather-storm)."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en milisegundos (0 = no expira).",
                    "default": 5000
                },
                "category": {
                    "type": "string",
                    "description": "Categoría (ej: email, msg, transfer)."
                },
                "transient": {
                    "type": "boolean",
                    "description": "Notificación transitoria (desaparece rápido).",
                    "default": False
                }
            },
            "required": ["title", "message"]
        }
    },
    {
        "name": "notify_contextual",
        "description": "Notificación contextual: la IA notifica cuando completa una tarea. Usa esto cuando termines de hacer algo importante.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Nombre de la tarea completada (ej: 'Envío de correo', 'Backup de DB')."
                },
                "result": {
                    "type": "string",
                    "description": "Resultado breve de la tarea."
                },
                "importance": {
                    "type": "string",
                    "enum": ["low", "medium", "high", "critical"],
                    "description": "Importancia de la notificación.",
                    "default": "medium"
                },
                "icon": {
                    "type": "string",
                    "description": "Icono (ej: mail-send, document-save, dialog-information)."
                }
            },
            "required": ["task", "result"]
        }
    },
    {
        "name": "format_whatsapp",
        "description": "Formatea texto para WhatsApp con emojis, negritas, listas anidadas y elementos rich text.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "elements": {
                    "type": "array",
                    "description": "Array de elementos a formatear.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "type": {"type": "string", "enum": ["heading", "bold", "italic", "strikethrough", "code", "text", "list", "emoji", "link", "newline", "divider"]},
                            "text": {"type": "string"},
                            "items": {"type": "array", "items": {"type": "object"}},
                            "url": {"type": "string"},
                            "name": {"type": "string"}
                        },
                        "required": ["type"]
                    }
                },
                "copy_to_clipboard": {
                    "type": "boolean",
                    "description": "Copiar resultado al clipboard.",
                    "default": True
                }
            },
            "required": ["elements"]
        }
    },
    {
        "name": "whatsapp_link",
        "description": "Genera enlace de WhatsApp con mensaje prellenado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Número de teléfono con código país (ej: 521234567890)."
                },
                "message": {
                    "type": "string",
                    "description": "Mensaje prellenado."
                },
                "copy_to_clipboard": {
                    "type": "boolean",
                    "description": "Copiar enlace al clipboard.",
                    "default": True
                }
            },
            "required": ["phone", "message"]
        }
    },
    {
        "name": "format_email",
        "description": "Compone cuerpo de email con formato (plain text, HTML, o ambos).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Nombre del destinatario (para saludo)."
                },
                "subject": {
                    "type": "string",
                    "description": "Asunto del correo."
                },
                "greeting": {
                    "type": "string",
                    "description": "Saludo personalizado (default: 'Hola {to},')."
                },
                "body": {
                    "type": "string",
                    "description": "Cuerpo principal del correo."
                },
                "bullets": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Lista de puntos a incluir."
                },
                "signature": {
                    "type": "string",
                    "description": "Firma del correo."
                },
                "format": {
                    "type": "string",
                    "enum": ["plain", "html", "both"],
                    "description": "Formato de salida.",
                    "default": "both"
                },
                "copy_to_clipboard": {
                    "type": "boolean",
                    "description": "Copiar resultado al clipboard.",
                    "default": False
                }
            },
            "required": ["body"]
        }
    },
    {
        "name": "email_send",
        "description": "Envía un correo electrónico usando msmtp. Requiere configuración previa en ~/.msmtprc o en la tabla access_credentials.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Destinatario del correo."
                },
                "subject": {
                    "type": "string",
                    "description": "Asunto del correo."
                },
                "body": {
                    "type": "string",
                    "description": "Cuerpo del correo (texto plano o HTML)."
                },
                "cc": {
                    "type": "string",
                    "description": "CC (opcional)."
                },
                "bcc": {
                    "type": "string",
                    "description": "BCC (opcional)."
                },
                "html": {
                    "type": "boolean",
                    "description": "Si el cuerpo es HTML.",
                    "default": False
                },
                "attachments": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Rutas de archivos adjuntos (opcional)."
                }
            },
            "required": ["to", "subject", "body"]
        }
    },
    {
        "name": "email_configure",
        "description": "Configura msmtp con credenciales SMTP. Guarda en ~/.msmtprc y en la DB.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "smtp_host": {
                    "type": "string",
                    "description": "Servidor SMTP (ej: smtp.gmail.com)."
                },
                "smtp_port": {
                    "type": "integer",
                    "description": "Puerto SMTP.",
                    "default": 587
                },
                "username": {
                    "type": "string",
                    "description": "Usuario SMTP."
                },
                "password": {
                    "type": "string",
                    "description": "Contraseña SMTP."
                },
                "from_name": {
                    "type": "string",
                    "description": "Nombre del remitente."
                },
                "from_email": {
                    "type": "string",
                    "description": "Email del remitente."
                },
                "tls": {
                    "type": "boolean",
                    "description": "Usar TLS.",
                    "default": True
                }
            },
            "required": ["smtp_host", "username", "password", "from_email"]
        }
    },
    {
        "name": "email_test",
        "description": "Envía un correo de prueba para verificar la configuración SMTP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "to": {
                    "type": "string",
                    "description": "Email de prueba (default: remitente)."
                }
            }
        }
    },
    {
        "name": "email_discover_settings",
        "description": "Auto-descubre configuración SMTP para un dominio. Busca MX records y prueba puertos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email completo (ej: user@gmail.com) o dominio (gmail.com)."
                }
            },
            "required": ["email"]
        }
    },
    {
        "name": "email_setup_wizard",
        "description": "Wizard completo: descubre SMTP, configura msmtp, guarda en DB encriptado, y prueba conexión.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email completo (ej: user@gmail.com)."
                },
                "password": {
                    "type": "string",
                    "description": "Contraseña o App Password."
                },
                "display_name": {
                    "type": "string",
                    "description": "Nombre para mostrar (opcional)."
                }
            },
            "required": ["email", "password"]
        }
    },
    {
        "name": "reminder_add",
        "description": "Programa un recordatorio o temporizador omnicanal (Telegram, escritorio Pop!_OS, aviso visual en teclado ASUS y lámpara Lux).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "Texto del recordatorio o tarea (ej: 'Revisar entrenamiento de modelo', 'Sacar la comida')"},
                "due": {"type": "string", "description": "Tiempo relativo o natural (ej: '15m', '2h', '18:30', 'en 45 segundos')"},
                "priority": {"type": "string", "enum": ["normal", "important", "critical"], "description": "Nivel de urgencia de la notificación", "default": "normal"}
            },
            "required": ["title", "due"]
        }
    },
    {
        "name": "reminder_list",
        "description": "Lista todos los recordatorios y temporizadores pendientes de vencer.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "reminder_cancel",
        "description": "Cancela y elimina un recordatorio por su ID numérico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "reminder_id": {"type": "integer", "description": "ID numérico del recordatorio a cancelar"}
            },
            "required": ["reminder_id"]
        }
    },
    # ── Email IMAP (Read/Receive) ──────────────────────────
    {
        "name": "email_list",
        "description": "Listar correos recientes en la bandeja de entrada. Retorna asunto, remitente, fecha y si tiene archivos adjuntos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "folder": {"type": "string", "description": "Carpeta del correo (default: INBOX)", "default": "INBOX"},
                "limit": {"type": "integer", "description": "Número de correos a mostrar (default 20)", "default": 20},
                "unread_only": {"type": "boolean", "description": "Solo mostrar no leídos", "default": False}
            }
        }
    },
    {
        "name": "email_read",
        "description": "Leer el contenido completo de un correo específico por su ID interno. Muestra headers, cuerpo (texto plano y HTML) y adjuntos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "ID interno del mensaje (obtener de email_list)"},
                "folder": {"type": "string", "description": "Carpeta del correo (default: INBOX)", "default": "INBOX"}
            },
            "required": ["message_id"]
        }
    },
    {
        "name": "email_search",
        "description": "Buscar correos por asunto, remitente o contenido en toda la bandeja de entrada.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Texto de búsqueda (asunto, remitente, o contenido)"},
                "folder": {"type": "string", "description": "Carpeta (default: INBOX)", "default": "INBOX"},
                "limit": {"type": "integer", "description": "Máximo de resultados (default 20)", "default": 20}
            },
            "required": ["query"]
        }
    },
    {
        "name": "email_folders",
        "description": "Listar todas las carpetas/carpeta disponibles en el buzón de correo.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "email_mark_read",
        "description": "Marcar un correo como leído.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "ID interno del mensaje"},
                "folder": {"type": "string", "description": "Carpeta (default: INBOX)", "default": "INBOX"}
            },
            "required": ["message_id"]
        }
    },
    {
        "name": "email_delete",
        "description": "Eliminar un correo por su ID interno.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "message_id": {"type": "string", "description": "ID interno del mensaje"},
                "folder": {"type": "string", "description": "Carpeta (default: INBOX)", "default": "INBOX"}
            },
            "required": ["message_id"]
        }
    },
]

def _format_whatsapp_element(element: dict, indent: int = 0) -> str:
    """Format a single WhatsApp element."""
    etype = element.get("type", "text")
    text = element.get("text", "")
    items = element.get("items", [])
    url = element.get("url", "")
    name = element.get("name", "")
    
    prefix = "  " * indent
    
    if etype == "heading":
        return f"*{text}*"
    elif etype == "bold":
        return f"*{text}*"
    elif etype == "italic":
        return f"_{text}_"
    elif etype == "strikethrough":
        return f"~{text}~"
    elif etype == "code":
        return f"```{text}```"
    elif etype == "text":
        return f"{prefix}{text}"
    elif etype == "emoji":
        # Common emoji names to unicode
        emojis = {
            "check": "✅", "x": "❌", "warning": "⚠️", "star": "⭐",
            "heart": "❤️", "fire": "🔥", "rocket": "🚀", "thumbsup": "👍",
            "clap": "👏", "wave": "👋", "sad": "😢", "happy": "😊",
            "think": "🤔", "eyes": "👀", "100": "💯", "tada": "🎉",
            "bulb": "💡", "lock": "🔒", "unlock": "🔓", "bell": "🔔",
            "mail": "📧", "phone": "📞", "calendar": "📅", "clock": "⏰",
            "gear": "⚙️", "wrench": "🔧", "hammer": "🔨", "key": "🔑",
            "house": "🏠", "building": "🏢", "globe": "🌍", "link": "🔗",
            "paperclip": "📎", "memo": "📝", "book": "📖", "lightning": "⚡"
        }
        emoji_char = emojis.get(name.lower(), f"[{name}]")
        return f"{emoji_char}"
    elif etype == "link":
        if text:
            return f"{text}: {url}"
        return url
    elif etype == "list":
        bullets = ["•", "◦", "▪"]
        result = []
        for i, item in enumerate(items):
            if isinstance(item, dict):
                item_text = item.get("text", "")
                sub_items = item.get("items", [])
                bullet = bullets[min(indent, len(bullets) - 1)]
                result.append(f"{prefix}{bullet} {item_text}")
                if sub_items:
                    for sub in sub_items:
                        if isinstance(sub, dict):
                            result.append(_format_whatsapp_element(sub, indent + 1))
                        else:
                            sub_bullet = bullets[min(indent + 1, len(bullets) - 1)]
                            result.append(f"{prefix}  {sub_bullet} {sub}")
            else:
                bullet = bullets[min(indent, len(bullets) - 1)]
                result.append(f"{prefix}{bullet} {item}")
        return "\n".join(result)
    elif etype == "newline":
        return ""
    elif etype == "divider":
        return "─────────────────"
    else:
        return f"{prefix}{text}"



def _discover_mx_records(domain: str) -> list:
    """Discover MX records for a domain."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX')
        mx_records = []
        for rdata in answers:
            mx_records.append({
                "host": str(rdata.exchange).rstrip('.'),
                "priority": rdata.preference
            })
        mx_records.sort(key=lambda x: x["priority"])
        return mx_records
    except Exception:
        return []



def _probe_smtp(host: str, ports: list = [587, 465, 25]) -> dict:
    """Probe SMTP server for supported ports and TLS."""
    import socket
    
    for port in ports:
        try:
            sock = socket.create_connection((host, port), timeout=5)
            banner = sock.recv(1024).decode('utf-8', errors='ignore')
            
            if port == 465:
                # SSL port
                sock.close()
                return {"port": port, "tls": True, "ssl": True, "banner": banner.strip()}
            else:
                # Try STARTTLS
                sock.send(b"EHLO test\r\n")
                sock.recv(1024)
                sock.send(b"STARTTLS\r\n")
                resp = sock.recv(1024).decode('utf-8', errors='ignore')
                sock.close()
                
                if "220" in resp:
                    return {"port": port, "tls": True, "ssl": False, "banner": banner.strip()}
                else:
                    return {"port": port, "tls": False, "ssl": False, "banner": banner.strip()}
        except Exception:
            continue
    
    return None



# ── Handlers ───────────────────────────────────────────────
def _send_notification_handler(title: str, message: str, urgency: str = "normal", icon: str = None, timeout: int = 5000, category: str = None, transient: bool = False) -> str:
    """Send desktop notification with advanced options."""
    try:
        cmd = ["notify-send"]
        
        # Urgency
        if urgency in ["low", "normal", "critical"]:
            cmd.extend(["-u", urgency])
        
        # Timeout
        if timeout > 0:
            cmd.extend(["-t", str(timeout)])
        
        # Icon
        if icon:
            if icon.startswith("/") or icon.startswith("~"):
                cmd.extend(["-i", os.path.expanduser(icon)])
            else:
                # Stock icon name
                cmd.extend(["-i", icon])
        
        # Category
        if category:
            cmd.extend(["-c", category])
        
        # Transient
        if transient:
            cmd.append("-e")
        
        # App name
        cmd.extend(["-a", "AI Lab"])
        
        # Title and message
        cmd.append(title)
        if message:
            cmd.append(message)
        
        subprocess.run(cmd, capture_output=True, timeout=5)
        
        log_operation("send_notification", {"title": title, "urgency": urgency}, "sent")
        
        result = f"🔔 Notificación enviada: {title}"
        if urgency == "critical":
            result += " (CRÍTICA)"
        elif urgency == "low":
            result += " (baja prioridad)"
        
        return result
    
    except FileNotFoundError:
        return "Error: notify-send no encontrado"
    except Exception as e:
        return f"Error enviando notificación: {e}"


SPOTIFY_PLAYER = os.path.join(HOME, ".cargo/bin/spotify_player")



def _notify_contextual_handler(task: str, result: str, importance: str = "medium", icon: str = None) -> str:
    """Send contextual notification when completing a task."""
    # Determine icon based on importance and task
    if not icon:
        if importance == "critical":
            icon = "dialog-error"
        elif importance == "high":
            icon = "dialog-warning"
        elif "email" in task.lower() or "correo" in task.lower():
            icon = "mail-send"
        elif "backup" in task.lower() or "respaldo" in task.lower():
            icon = "document-save"
        elif "deploy" in task.lower() or "despliegue" in task.lower():
            icon = "system-run"
        elif "error" in result.lower() or "❌" in result:
            icon = "dialog-error"
        elif "✅" in result or "completado" in result.lower():
            icon = "emblem-ok"
        else:
            icon = "dialog-information"

    # Build message
    msg = f"✅ {task}\n{result[:150]}"

    try:
        subprocess.run(
            ["notify-send", "-u", importance if importance in ["low", "normal", "critical"] else "normal",
             "-i", icon, "-a", "AI Lab", "-t", "5000",
             f"🤖 Tarea Completada", msg],
            capture_output=True,
            timeout=3
        )
    except Exception:
        pass

    log_operation("notify_contextual", {"task": task, "importance": importance}, "sent")
    return f"🔔 Notificación enviada: {task}"


# ── Enhanced Search Implementations ─────────────────────────

def _format_whatsapp_handler(elements: list, copy_to_clipboard: bool = True) -> str:
    """Format text for WhatsApp with rich formatting."""
    try:
        lines = []
        for element in elements:
            formatted = _format_whatsapp_element(element)
            lines.append(formatted)
        
        result = "\n".join(lines)
        
        if copy_to_clipboard:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=result.encode(),
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                pass
        
        log_operation("format_whatsapp", {"elements_count": len(elements)}, result[:100])
        return result
    
    except Exception as e:
        return f"Error formateando: {e}"



def _whatsapp_link_handler(phone: str, message: str, copy_to_clipboard: bool = True) -> str:
    """Generate WhatsApp link with pre-filled message."""
    try:
        # Clean phone number (remove spaces, dashes, plus)
        clean_phone = phone.replace(" ", "").replace("-", "").replace("+", "").replace("(", "").replace(")", "")
        
        # Ensure it starts with country code
        if not clean_phone.startswith("52") and len(clean_phone) == 10:
            clean_phone = "52" + clean_phone
        
        # URL encode the message
        encoded_message = quote(message)
        
        # Generate link
        link = f"https://wa.me/{clean_phone}?text={encoded_message}"
        
        if copy_to_clipboard:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=link.encode(),
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                pass
        
        result = f"📱 Enlace de WhatsApp:\n{link}\n\n"
        result += f"📞 Teléfono: {clean_phone}\n"
        result += f"💬 Mensaje: {message[:50]}{'...' if len(message) > 50 else ''}"
        
        log_operation("whatsapp_link", {"phone": clean_phone}, link)
        return result
    
    except Exception as e:
        return f"Error generando enlace: {e}"



def _format_email_handler(to: str = None, subject: str = None, greeting: str = None, 
                      body: str = "", bullets: list = None, signature: str = None,
                      format: str = "both", copy_to_clipboard: bool = False) -> str:
    """Compose email body with formatting."""
    try:
        result = {}
        
        # Build greeting
        if greeting:
            saludo = greeting
        elif to:
            saludo = f"Hola {to},"
        else:
            saludo = ""
        
        # Build plain text version
        plain_lines = []
        if saludo:
            plain_lines.append(saludo)
            plain_lines.append("")
        
        plain_lines.append(body)
        
        if bullets:
            plain_lines.append("")
            for bullet in bullets:
                plain_lines.append(f"• {bullet}")
        
        if signature:
            plain_lines.append("")
            plain_lines.append(signature)
        
        plain_text = "\n".join(plain_lines)
        
        # Build HTML version
        html_lines = []
        if saludo:
            html_lines.append(f"<p>{saludo}</p>")
        
        html_lines.append(f"<p>{body}</p>")
        
        if bullets:
            html_lines.append("<ul>")
            for bullet in bullets:
                html_lines.append(f"<li>{bullet}</li>")
            html_lines.append("</ul>")
        
        if signature:
            html_lines.append(f"<p style='color: #666; margin-top: 20px;'>{signature.replace(chr(10), '<br>')}</p>")
        
        html_text = "\n".join(html_lines)
        
        # Prepare output
        if format == "plain":
            result_text = plain_text
        elif format == "html":
            result_text = html_text
        else:  # both
            result_text = f"=== PLAIN TEXT ===\n{plain_text}\n\n=== HTML ===\n{html_text}"
        
        if copy_to_clipboard:
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=plain_text.encode(),
                    capture_output=True,
                    timeout=5
                )
            except Exception:
                pass
        
        log_operation("format_email", {"to": to, "format": format}, result_text[:100])
        return result_text
    
    except Exception as e:
        return f"Error formateando email: {e}"

def _email_send_handler(to: str, subject: str, body: str, cc: str = None, bcc: str = None, html: bool = False, attachments: list = None, from_email: str = None) -> str:
    try:
        import os
        import subprocess
        import mimetypes
        import json
        import re
        from email.message import EmailMessage
        from email.utils import formatdate, make_msgid

        msg = EmailMessage()
        msg["Date"] = formatdate(localtime=True)
        msg["Message-ID"] = make_msgid(domain="castelancarpinteyro.com")
        msg["Subject"] = subject
        msg["To"] = to

        if cc:
            msg["Cc"] = cc
        if bcc:
            msg["Bcc"] = bcc

        # If from_email is not provided, read default from ~/.msmtprc
        if not from_email:
            config_path = os.path.expanduser("~/.msmtprc")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        for line in f:
                            if line.strip().startswith("from "):
                                from_email = line.strip().split(" ", 1)[1].strip()
                                break
                except Exception:
                    pass

        if from_email:
            msg["From"] = from_email

        # Set content (plain text or html)
        if html:
            msg.set_content(body, subtype="html", charset="utf-8")
        else:
            msg.set_content(body, charset="utf-8")

        # Normalize attachments input
        file_list = []
        if isinstance(attachments, str):
            try:
                parsed = json.loads(attachments)
                if isinstance(parsed, list):
                    file_list = parsed
                else:
                    file_list = [attachments]
            except Exception:
                file_list = [p.strip() for p in attachments.split(",") if p.strip()]
        elif isinstance(attachments, (list, tuple)):
            file_list = list(attachments)

        # Fallback: if no attachments explicitly passed, scan body and subject for absolute file paths that exist
        if not file_list and body:
            potential_paths = re.findall(r'(?:/[a-zA-Z0-9_\.\-]+)+', body)
            for p in potential_paths:
                if os.path.isfile(p) and not p.startswith('/dev/') and not p.startswith('/proc/'):
                    file_list.append(p)

        attached_files = []
        missing_files = []

        for filepath in file_list:
            if not filepath or not isinstance(filepath, str):
                continue
            clean_path = os.path.expanduser(filepath.strip())
            if os.path.isfile(clean_path):
                ctype, encoding = mimetypes.guess_type(clean_path)
                if ctype is None or encoding is not None:
                    ctype = "application/octet-stream"
                maintype, subtype = ctype.split("/", 1)

                filename = os.path.basename(clean_path)
                with open(clean_path, "rb") as fp:
                    file_data = fp.read()
                    msg.add_attachment(
                        file_data,
                        maintype=maintype,
                        subtype=subtype,
                        filename=filename
                    )
                attached_files.append(filename)
            else:
                missing_files.append(filepath)

        # Send with smtplib (more reliable than msmtp subprocess)
        import smtplib
        smtp_host = "74.208.62.188"
        smtp_port = 465
        smtp_user = None
        smtp_pass = None

        # Read credentials from ~/.msmtprc
        config_path = os.path.expanduser("~/.msmtprc")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("host "):
                            smtp_host = line.split(None, 1)[1]
                        elif line.startswith("user "):
                            smtp_user = line.split(None, 1)[1]
                        elif line.startswith("password "):
                            smtp_pass = line.split(None, 1)[1]
                        elif line.startswith("port "):
                            smtp_port = int(line.split(None, 1)[1])
            except Exception:
                pass

        if not smtp_user or not smtp_pass:
            return "Error: No se encontraron credenciales SMTP en ~/.msmtprc"

        try:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=15)
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
            server.quit()
        except Exception as e:
            return f"Error SMTP: {e}"

        log_operation("email_send", {"to": to, "subject": subject, "attachments": attached_files}, "OK")
        res = f"Correo enviado exitosamente a {to}"
        if attached_files:
            res += f" con {len(attached_files)} archivo(s) adjunto(s): {', '.join(attached_files)}"
        if missing_files:
            res += f" (Advertencia: no se encontraron los archivos: {', '.join(missing_files)})"
        return res

    except Exception as e:
        return f"Error en tool_email_send: {e}"



def _email_configure_handler(smtp_host: str, username: str, password: str, from_email: str, smtp_port: int = 587, from_name: str = None, tls: bool = True) -> str:
    try:
        home = os.path.expanduser("~")
        config_path = os.path.join(home, ".msmtprc")
        
        # Build config
        config = f"""account default
host {smtp_host}
port {smtp_port}
auth on
user {username}
password {password}
"""
        
        if tls:
            config += "tls on\ntls_starttls on\n"
        
        if from_name and from_email:
            config += f"from {from_email}\n"
        
        # Write config
        with open(config_path, "w") as f:
            f.write(config)
        
        # Set permissions
        os.chmod(config_path, 0o600)
        
        # Save to DB
        try:
            import sqlite3
            db_path = os.path.join(home, ".config/ai-memory.db")
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO access_credentials (name, credential_type, host, port, username, password_encrypted, extra_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, ("default_smtp", "smtp", smtp_host, smtp_port, username, password, 
                  json.dumps({"from_name": from_name, "from_email": from_email, "tls": tls})))
            conn.commit()
            conn.close()
        except Exception as db_err:
            pass
        
        log_operation("email_configure", {"host": smtp_host}, "OK")
        return f"SMTP configurado: {smtp_host}:{smtp_port}"
    
    except Exception as e:
        return f"Error configurando SMTP: {e}"



def _email_test_handler(to: str = None) -> str:
    try:
        home = os.path.expanduser("~")
        config_path = os.path.join(home, ".msmtprc")
        
        if not os.path.exists(config_path):
            return "Error: No hay configuración SMTP. Usa email_configure primero."
        
        # Read from email from config
        from_email = None
        with open(config_path, "r") as f:
            for line in f:
                if line.startswith("from "):
                    from_email = line.split(" ", 1)[1].strip()
        
        if not to:
            to = from_email
        
        if not to:
            return "Error: No se pudo determinar el destinatario."
        
        return _email_send_handler(
            to=to,
            subject="Test de correo - AI Lab",
            body="Este es un correo de prueba desde tu sistema de IA local.\n\nSi lo recibes, la configuración SMTP funciona correctamente."
        )
    
    except Exception as e:
        return f"Error: {e}"


# ── Communication Implementations ──────────────────────────

def _email_discover_settings_handler(email: str) -> str:
    """Auto-discover SMTP settings for an email domain."""
    try:
        # Extract domain
        if "@" in email:
            domain = email.split("@")[1]
        else:
            domain = email
        
        # Discover MX records
        mx_records = _discover_mx_records(domain)
        
        if not mx_records:
            return f"No se encontraron MX records para {domain}"
        
        result = f"📧 Configuración descubierta para {domain}:\n\n"
        result += "MX Records:\n"
        
        best_smtp = None
        
        for mx in mx_records:
            result += f"  • {mx['host']} (prioridad: {mx['priority']})\n"
            
            # Probe the first MX server
            if not best_smtp:
                probe = _probe_smtp(mx["host"])
                if probe:
                    best_smtp = {
                        "host": mx["host"],
                        "port": probe["port"],
                        "tls": probe["tls"],
                        "ssl": probe.get("ssl", False)
                    }
        
        if best_smtp:
            result += f"\n✅ SMTP detectado:\n"
            result += f"  Host: {best_smtp['host']}\n"
            result += f"  Puerto: {best_smtp['port']}\n"
            result += f"  TLS: {'Sí' if best_smtp['tls'] else 'No'}\n"
            result += f"  SSL: {'Sí' if best_smtp['ssl'] else 'No'}\n"
        else:
            result += "\n⚠️ No se pudo detectar SMTP automáticamente"
        
        return result
    
    except Exception as e:
        return f"Error descubriendo configuración: {e}"



def _email_setup_wizard_handler(email: str, password: str, display_name: str = None) -> str:
    """Complete email setup wizard: discover, configure, save, test."""
    try:
        import sqlite3
        
        # Extract domain and username
        if "@" not in email:
            return "Error: Se requiere un email completo (ej: user@gmail.com)"
        
        username = email.split("@")[0]
        domain = email.split("@")[1]
        
        result = f"🔧 Wizard de configuración para {email}\n\n"
        
        # Step 1: Discover SMTP settings
        result += "1️⃣ Descubriendo configuración SMTP...\n"
        mx_records = _discover_mx_records(domain)
        
        if not mx_records:
            return result + "❌ No se encontraron MX records. Configura manualmente con email_configure."
        
        smtp_host = mx_records[0]["host"]
        probe = _probe_smtp(smtp_host)
        
        if not probe:
            return result + "❌ No se pudo detectar el servidor SMTP."
        
        smtp_port = probe["port"]
        tls = probe["tls"]
        
        result += f"  ✅ SMTP: {smtp_host}:{smtp_port}\n"
        result += f"  ✅ TLS: {'Sí' if tls else 'No'}\n\n"
        
        # Step 2: Configure msmtp
        result += "2️⃣ Configurando msmtp...\n"
        
        home = os.path.expanduser("~")
        config_path = os.path.join(home, ".msmtprc")
        
        config = f"""account default
host {smtp_host}
port {smtp_port}
auth on
user {email}
password {password}
"""
        if tls:
            if probe.get("ssl"):
                config += "tls on\n"
            else:
                config += "tls on\ntls_starttls on\n"
        
        config += f"from {email}\n"
        
        with open(config_path, "w") as f:
            f.write(config)
        os.chmod(config_path, 0o600)
        
        result += "  ✅ msmtp configurado\n\n"
        
        # Step 3: Save to DB (encrypted)
        result += "3️⃣ Guardando en base de datos...\n"
        
        encrypted_password = encrypt_value(password)
        
        db_path = os.path.join(home, ".config/ai-memory.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if exists
        cursor.execute("SELECT id FROM access_credentials WHERE name = ?", (f"smtp_{domain}",))
        existing = cursor.fetchone()
        
        extra_data = json.dumps({
            "email": email,
            "display_name": display_name or username,
            "tls": tls,
            "ssl": probe.get("ssl", False)
        })
        
        if existing:
            cursor.execute("""
                UPDATE access_credentials 
                SET host=?, port=?, username=?, password_encrypted=?, extra_data=?, updated_at=CURRENT_TIMESTAMP
                WHERE name=?
            """, (smtp_host, smtp_port, email, encrypted_password, extra_data, f"smtp_{domain}"))
        else:
            cursor.execute("""
                INSERT INTO access_credentials (name, credential_type, host, port, username, password_encrypted, extra_data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (f"smtp_{domain}", "smtp", smtp_host, smtp_port, email, encrypted_password, extra_data))
        
        conn.commit()
        conn.close()
        
        result += "  ✅ Credenciales guardadas (encriptadas)\n\n"
        
        # Step 4: Test
        result += "4️⃣ Probando conexión...\n"
        
        test_result = _email_test_handler(email)
        
        if "enviado" in test_result.lower() or "ok" in test_result.lower():
            result += f"  ✅ {test_result}\n\n"
            result += f"🎉 ¡Configuración completada!\n"
            result += f"   Email: {email}\n"
            result += f"   SMTP: {smtp_host}:{smtp_port}\n"
            result += f"   Puedes usar email_send para enviar correos."
        else:
            result += f"  ⚠️ {test_result}\n\n"
            result += "La configuración se guardó pero hubo un error en la prueba."
        
        return result
    
    except Exception as e:
        return f"Error en wizard: {e}"



def _reminder_add_handler(title: str, due: str, priority: str = "normal") -> str:
    """Programa un recordatorio o temporizador omnicanal."""
    try:
        from reminder_engine import reminder_engine
        res = reminder_engine.add_reminder(title=title, due=due, priority=priority)
        return f"⏰ Recordatorio programado [#{res['id']}]: '{res['title']}' para dentro de {res['time_left']} ({res['due_at']}) [Prioridad: {res['priority'].upper()}]"
    except Exception as e:
        return f"Error programando recordatorio: {e}"



def _reminder_list_handler() -> str:
    """Lista los recordatorios y temporizadores pendientes."""
    try:
        from reminder_engine import reminder_engine
        items = reminder_engine.list_pending_reminders()
        if not items:
            return "No hay recordatorios pendientes."
        lines = [f"📋 Recordatorios pendientes ({len(items)}):"]
        for i in items:
            lines.append(f"  • [#{i['id']}] {i['title']} ➔ Vence en {i['time_left']} ({i['due_at']}) [{i['priority'].upper()}]")
        return "\n".join(lines)
    except Exception as e:
        return f"Error listando recordatorios: {e}"



def _reminder_cancel_handler(reminder_id: int) -> str:
    """Cancela un recordatorio por ID."""
    try:
        from reminder_engine import reminder_engine
        ok = reminder_engine.cancel_reminder(int(reminder_id))
        if ok:
            return f"✅ Recordatorio #{reminder_id} cancelado."
        return f"No se encontró el recordatorio #{reminder_id}."
    except Exception as e:
        return f"Error cancelando recordatorio: {e}"


# ── Email IMAP Handlers ───────────────────────────────────

def _get_imap_config():
    """Read IMAP config from ~/.msmtprc (same credentials, different server/port)."""
    config = {}
    try:
        with open(os.path.expanduser("~/.msmtprc")) as f:
            for line in f:
                line = line.strip()
                if line.startswith("host "):
                    config["host"] = line.split(None, 1)[1]
                elif line.startswith("user "):
                    config["user"] = line.split(None, 1)[1]
                elif line.startswith("password "):
                    config["password"] = line.split(None, 1)[1]
    except Exception:
        pass
    if not config.get("host") or not config.get("user"):
        return None
    # Derive IMAP host from SMTP host
    host = config["host"]
    if not host.startswith("mail."):
        imap_host = f"mail.{host}"
    else:
        imap_host = host
    return {
        "host": imap_host,
        "port": 993,
        "user": config["user"],
        "password": config.get("password", ""),
    }


def _imap_connect(folder: str = "INBOX"):
    """Connect to IMAP and return (server, mailbox)."""
    import imaplib
    cfg = _get_imap_config()
    if not cfg:
        raise RuntimeError("No hay configuración de correo. Usa email_configure o email_setup_wizard primero.")
    mail = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
    mail.login(cfg["user"], cfg["password"])
    mail.select(folder)
    return mail


def _email_list_handler(folder: str = "INBOX", limit: int = 20, unread_only: bool = False) -> str:
    try:
        mail = _imap_connect(folder)
        if unread_only:
            status, msgs = mail.search(None, "UNSEEN")
        else:
            status, msgs = mail.search(None, "ALL")
        if status != "OK":
            return "Error buscando correos."
        ids = msgs[0].split()
        if not ids:
            return f"📭 No hay correos en {folder}{' (no leídos)' if unread_only else ''}."
        # Get last N
        recent_ids = ids[-min(limit, len(ids)):]
        output = f"📬 **{len(recent_ids)} correos en {folder}:**\n\n"
        for msg_id in reversed(recent_ids):
            status, data = mail.fetch(msg_id, "(RFC822.HEADER)")
            if status != "OK":
                continue
            import email
            msg = email.message_from_bytes(data[0][1])
            subject = msg.get("Subject", "(sin asunto)")
            from_addr = msg.get("From", "?")
            date = msg.get("Date", "?")[:25]
            has_attach = any(part.get("Content-Disposition", "").startswith("attachment") for part in msg.walk())
            attach_icon = " 📎" if has_attach else ""
            output += f"• **{subject}**{attach_icon}\n  De: {from_addr} | {date} | ID: {msg_id.decode()}\n"
        mail.logout()
        log_operation("email_list", {"folder": folder}, f"{len(recent_ids)} emails")
        return output
    except Exception as e:
        return f"Error listando correos: {e}"


def _email_read_handler(message_id: str, folder: str = "INBOX") -> str:
    try:
        mail = _imap_connect(folder)
        status, data = mail.fetch(message_id.encode(), "(RFC822)")
        if status != "OK":
            return f"No se encontró el correo con ID: {message_id}"
        import email
        msg = email.message_from_bytes(data[0][1])
        subject = msg.get("Subject", "(sin asunto)")
        from_addr = msg.get("From", "?")
        to_addr = msg.get("To", "?")
        date = msg.get("Date", "?")
        output = f"📧 **{subject}**\n"
        output += f"De: {from_addr}\nPara: {to_addr}\nFecha: {date}\n\n"
        # Extract body
        body = ""
        attachments = []
        if msg.is_multipart():
            for part in msg.walk():
                ctype = part.get_content_type()
                disp = str(part.get("Content-Disposition", ""))
                if "attachment" in disp:
                    attachments.append(part.get_filename() or "adjunto")
                elif ctype == "text/plain" and not body:
                    body = part.get_payload(decode=True).decode(errors="replace")
        else:
            body = msg.get_payload(decode=True).decode(errors="replace")
        if body:
            output += f"**Mensaje:**\n{body[:3000]}\n"
        if attachments:
            output += f"\n📎 **Adjuntos:** {', '.join(attachments)}\n"
        mail.logout()
        log_operation("email_read", {"message_id": message_id}, "OK")
        return output
    except Exception as e:
        return f"Error leyendo correo: {e}"


def _email_search_handler(query: str, folder: str = "INBOX", limit: int = 20) -> str:
    try:
        mail = _imap_connect(folder)
        # Search by subject
        status, msgs = mail.search(None, f'(OR SUBJECT "{query}" FROM "{query}")')
        if status != "OK":
            return "Error en la búsqueda."
        ids = msgs[0].split()
        if not ids:
            return f"🔍 No se encontraron correos para: {query}"
        recent_ids = ids[-min(limit, len(ids)):]
        output = f"🔍 **{len(recent_ids)} resultados para '{query}' en {folder}:**\n\n"
        for msg_id in reversed(recent_ids):
            status, data = mail.fetch(msg_id, "(RFC822.HEADER)")
            if status != "OK":
                continue
            import email
            msg = email.message_from_bytes(data[0][1])
            subject = msg.get("Subject", "(sin asunto)")
            from_addr = msg.get("From", "?")
            date = msg.get("Date", "?")[:25]
            output += f"• **{subject}**\n  De: {from_addr} | {date} | ID: {msg_id.decode()}\n"
        mail.logout()
        log_operation("email_search", {"query": query}, f"{len(recent_ids)} results")
        return output
    except Exception as e:
        return f"Error buscando correos: {e}"


def _email_folders_handler() -> str:
    try:
        cfg = _get_imap_config()
        if not cfg:
            return "No hay configuración de correo."
        import imaplib
        mail = imaplib.IMAP4_SSL(cfg["host"], cfg["port"])
        mail.login(cfg["user"], cfg["password"])
        status, folders = mail.list()
        mail.logout()
        if status != "OK":
            return "Error listando carpetas."
        output = "📁 **Carpetas de correo:**\n\n"
        for f in folders:
            name = f.decode().split('" "')[-1].strip('"') if '"' in f.decode() else f.decode().split()[-1]
            output += f"• {name}\n"
        log_operation("email_folders", {}, f"{len(folders)} folders")
        return output
    except Exception as e:
        return f"Error listando carpetas: {e}"


def _email_mark_read_handler(message_id: str, folder: str = "INBOX") -> str:
    try:
        mail = _imap_connect(folder)
        mail.store(message_id.encode(), "+FLAGS", "\\Seen")
        mail.logout()
        log_operation("email_mark_read", {"message_id": message_id}, "OK")
        return f"✅ Correo {message_id} marcado como leído."
    except Exception as e:
        return f"Error marcando correo: {e}"


def _email_delete_handler(message_id: str, folder: str = "INBOX") -> str:
    try:
        mail = _imap_connect(folder)
        mail.store(message_id.encode(), "+FLAGS", "\\Deleted")
        mail.expunge()
        mail.logout()
        log_operation("email_delete", {"message_id": message_id}, "OK")
        return f"🗑️ Correo {message_id} eliminado."
    except Exception as e:
        return f"Error eliminando correo: {e}"


# ── Dev Ops & Control Remoto ─────────────────────────────

HANDLERS = {
    "send_notification": _send_notification_handler,
    "notify_contextual": _notify_contextual_handler,
    "format_whatsapp": _format_whatsapp_handler,
    "whatsapp_link": _whatsapp_link_handler,
    "format_email": _format_email_handler,
    "email_send": _email_send_handler,
    "email_configure": _email_configure_handler,
    "email_test": _email_test_handler,
    "email_discover_settings": _email_discover_settings_handler,
    "email_setup_wizard": _email_setup_wizard_handler,
    "email_list": _email_list_handler,
    "email_read": _email_read_handler,
    "email_search": _email_search_handler,
    "email_folders": _email_folders_handler,
    "email_mark_read": _email_mark_read_handler,
    "email_delete": _email_delete_handler,
    "reminder_add": _reminder_add_handler,
    "reminder_list": _reminder_list_handler,
    "reminder_cancel": _reminder_cancel_handler,
}
