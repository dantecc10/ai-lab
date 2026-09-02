"""OSINT tools for username, email, domain, IP, and person search"""

import os
import sys
import subprocess
import json

from mcp_common.logging import log_operation
from mcp_common.security import is_safe_url
from mcp_common.audit import record_system_error

TOOLS = [
    {
        "name": "osint_username",
        "description": "Búsqueda OSINT de username en 3000+ plataformas (maigret/sherlock). Encuentra cuentas en redes sociales, foros, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "username": {
                    "type": "string",
                    "description": "Username a buscar (ej: dantecc10)."
                },
                "sites": {
                    "type": "string",
                    "description": "Sitios específicos separados por coma (ej: github,instagram,twitter)."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados a mostrar.",
                    "default": 50
                }
            },
            "required": ["username"]
        }
    },
    {
        "name": "osint_email",
        "description": "Investiga un email para encontrar cuentas asociadas en redes sociales y plataformas (holehe).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "email": {
                    "type": "string",
                    "description": "Email a investigar."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados.",
                    "default": 30
                }
            },
            "required": ["email"]
        }
    },
    {
        "name": "osint_domain",
        "description": "Inteligencia de dominio: registros DNS, WHOIS, subdominios, conectividad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Dominio a investigar (ej: example.com)."
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "osint_ip",
        "description": "Inteligencia de IP: geolocalización, ASN, reverse DNS, puertos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "ip_address": {
                    "type": "string",
                    "description": "Dirección IP a investigar."
                }
            },
            "required": ["ip_address"]
        }
    },
    {
        "name": "osint_person",
        "description": "Busca una persona por nombre en múltiples plataformas. Genera variaciones de username.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre completo de la persona."
                },
                "email": {
                    "type": "string",
                    "description": "Email conocido (opcional, mejora la búsqueda)."
                },
                "location": {
                    "type": "string",
                    "description": "Ubicación conocida (opcional)."
                }
            },
            "required": ["name"]
        }
    },
]

# ── Handlers ───────────────────────────────────────────────
def _osint_username_handler(username: str, sites: str = None, max_results: int = 50) -> str:
    """Search username across 3000+ platforms using maigret/sherlock."""
    try:
        import subprocess
        import json
        import os

        # Use maigret as primary (3302 sites)
        skills_bin = os.path.expanduser("~/scripting/gpu-tools/skills/.venv/bin")
        venv_python = os.path.join(skills_bin, "python") if os.path.exists(os.path.join(skills_bin, "python")) else sys.executable

        # Build maigret command
        cmd = [
            venv_python, "-m", "maigret",
            username,
            "--json",
            "--no-errors",
            "-t", str(min(max_results, 100))  # limit timeout
        ]

        # Add specific sites if provided
        if sites:
            site_list = [s.strip() for s in sites.split(",")]
            for site in site_list:
                cmd.extend(["-s", site])

        # Run maigret with timeout
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                env={**os.environ, "PATH": f"{skills_bin}:{os.environ.get('PATH', '')}"}
            )

            # Parse JSON output
            output = result.stdout
            if output:
                try:
                    data = json.loads(output)
                except json.JSONDecodeError:
                    # Try to extract JSON from output
                    import re
                    json_match = re.search(r'\{[\s\S]*\}', output)
                    if json_match:
                        data = json.loads(json_match.group())
                    else:
                        data = {}
            else:
                data = {}

        except subprocess.TimeoutExpired:
            data = {}
            output = "Maigret timeout - using fallback"
        except FileNotFoundError:
            data = {}
            output = "Maigret not found"

        # Format output
        if data:
            accounts = []
            for site_name, site_data in data.items():
                if isinstance(site_data, dict):
                    status = site_data.get("status", "unknown")
                    url = site_data.get("url_user", "")
                    if status in ["Claimed", "Found", "exists"]:
                        accounts.append({
                            "site": site_name,
                            "url": url,
                            "status": status
                        })

            if accounts:
                output = f"🔍 **Username: {username}**\n"
                output += f"📊 Encontrado en {len(accounts)} plataformas:\n\n"

                for acc in accounts[:max_results]:
                    output += f"• {acc['site']}: {acc['url']}\n"

                log_operation("osint_username", {"username": username}, f"{len(accounts)} accounts")
                return output

        # Fallback: try sherlock
        try:
            cmd = [
                venv_python, "-m", "sherlock",
                username,
                "--json",
                "--print-found"
            ]

            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                env={**os.environ, "PATH": f"{skills_bin}:{os.environ.get('PATH', '')}"}
            )

            if result.stdout:
                # Parse sherlock output
                accounts = []
                for line in result.stdout.split('\n'):
                    if 'http' in line.lower() and username.lower() in line.lower():
                        accounts.append(line.strip())

                if accounts:
                    output = f"🔍 **Username: {username}**\n"
                    output += f"📊 Sherlock encontró {len(accounts)} cuentas:\n\n"
                    for acc in accounts[:max_results]:
                        output += f"• {acc}\n"
                    log_operation("osint_username", {"username": username}, f"{len(accounts)} (sherlock)")
                    return output
        except Exception:
            pass

        return f"No se encontró el username '{username}' en las plataformas buscadas"

    except Exception as e:
        return f"Error en OSINT username: {e}"



def _osint_email_handler(email: str, max_results: int = 30) -> str:
    """Find social accounts from email using holehe."""
    try:
        import subprocess
        import json
        import os

        skills_bin = os.path.expanduser("~/scripting/gpu-tools/skills/.venv/bin")
        venv_python = os.path.join(skills_bin, "python") if os.path.exists(os.path.join(skills_bin, "python")) else sys.executable

        # Use holehe for email investigation
        cmd = [
            venv_python, "-m", "holehe",
            email,
            "--json"
        ]

        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120,
                env={**os.environ, "PATH": f"{skills_bin}:{os.environ.get('PATH', '')}"}
            )

            # Parse output
            output = result.stdout
            accounts = []

            if output:
                try:
                    data = json.loads(output)
                    if isinstance(data, list):
                        accounts = data
                    elif isinstance(data, dict):
                        accounts = data.get("accounts", [])
                except json.JSONDecodeError:
                    # Parse line by line
                    for line in output.split('\n'):
                        if 'http' in line.lower() or 'true' in line.lower():
                            accounts.append({"site": line.strip(), "exists": True})

        except subprocess.TimeoutExpired:
            accounts = []
        except FileNotFoundError:
            accounts = []

        # Fallback: check common platforms with requests
        if not accounts:
            try:
                import requests
                from bs4 import BeautifulSoup

                common_platforms = {
                    "GitHub": f"https://github.com/{email.split('@')[0]}",
                    "Twitter": f"https://twitter.com/{email.split('@')[0]}",
                    "Instagram": f"https://www.instagram.com/{email.split('@')[0]}/",
                }

                for platform, url in common_platforms.items():
                    try:
                        resp = requests.get(url, timeout=5, allow_redirects=False,
                                          headers={"User-Agent": "Mozilla/5.0"})
                        if resp.status_code == 200:
                            accounts.append({"site": platform, "url": url, "exists": True})
                    except Exception:
                        pass
            except Exception:
                pass

        # Format output
        if accounts:
            output = f"📧 **Email: {email}**\n"
            output += f"📊 Cuentas encontradas: {len(accounts)}\n\n"

            for acc in accounts[:max_results]:
                if isinstance(acc, dict):
                    site = acc.get("site", acc.get("name", "Unknown"))
                    url = acc.get("url", "")
                    if url:
                        output += f"• {site}: {url}\n"
                    else:
                        output += f"• {site}\n"
                else:
                    output += f"• {acc}\n"

            log_operation("osint_email", {"email": email}, f"{len(accounts)} accounts")
            return output

        return f"No se encontraron cuentas para el email: {email}"

    except Exception as e:
        return f"Error en OSINT email: {e}"



def _osint_domain_handler(domain: str) -> str:
    """Gather intelligence about a domain (DNS, WHOIS, subdomains)."""
    try:
        import dns.resolver
        import whois
        import tldextract
        import requests
        from bs4 import BeautifulSoup

        output = f"🌐 **Dominio: {domain}**\n\n"

        # Extract domain parts
        ext = tldextract.extract(domain)
        output += f"📌 Registrado: {ext.registered_domain}\n"
        output += f"📌 Subdominio: {ext.subdomain or '(ninguno)'}\n"
        output += f"📌 TLD: {ext.suffix}\n\n"

        # DNS Records
        output += "### 📡 Registros DNS\n"
        record_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]

        for rtype in record_types:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                records = [str(r) for r in answers]
                if records:
                    output += f"\n**{rtype}:**\n"
                    for r in records[:5]:
                        output += f"  • {r[:100]}\n"
            except Exception:
                pass

        # WHOIS
        output += "\n### 📋 WHOIS\n"
        try:
            w = whois.whois(domain)
            if w:
                if w.registrar:
                    output += f"• Registrar: {w.registrar}\n"
                if w.creation_date:
                    creation = w.creation_date
                    if isinstance(creation, list):
                        creation = creation[0]
                    output += f"• Creado: {creation}\n"
                if w.expiration_date:
                    exp = w.expiration_date
                    if isinstance(exp, list):
                        exp = exp[0]
                    output += f"• Expira: {exp}\n"
                if w.name_servers:
                    ns = w.name_servers if isinstance(w.name_servers, list) else [w.name_servers]
                    output += f"• Name Servers: {', '.join(ns[:3])}\n"
                if w.org:
                    output += f"• Organización: {w.org}\n"
                if w.country:
                    output += f"• País: {w.country}\n"
        except Exception as e:
            output += f"• Error WHOIS: {e}\n"

        # Check for common subdomains
        output += "\n### 🔍 Subdominios Comunes\n"
        common_subdomains = ["www", "mail", "ftp", "smtp", "pop", "webmail", "admin", "api", "dev", "staging"]
        found_subdomains = []

        for sub in common_subdomains:
            try:
                subdomain = f"{sub}.{domain}"
                dns.resolver.resolve(subdomain, "A")
                found_subdomains.append(subdomain)
                output += f"• ✅ {subdomain}\n"
            except Exception:
                pass

        if not found_subdomains:
            output += "• No se encontraron subdominios comunes\n"

        # Check HTTP/HTTPS
        output += "\n### 🌐 Conectividad\n"
        for protocol in ["https", "http"]:
            try:
                check_url = f"{protocol}://{domain}"
                if not is_safe_url(check_url):
                    output += f"• {protocol.upper()}: Bloqueado por seguridad\n"
                    continue
                resp = requests.get(check_url, timeout=5,
                                   allow_redirects=True,
                                   headers={"User-Agent": "Mozilla/5.0"})
                output += f"• {protocol.upper()}: {resp.status_code} ({resp.url[:50]})\n"
            except Exception as e:
                output += f"• {protocol.upper()}: No disponible\n"

        log_operation("osint_domain", {"domain": domain}, "OK")
        return output

    except Exception as e:
        return f"Error en OSINT dominio: {e}"



def _osint_ip_handler(ip_address: str) -> str:
    """Gather intelligence about an IP address."""
    try:
        import requests
        from ipwhois import IPWhois

        output = f"🌐 **IP: {ip_address}**\n\n"

        # IP WHOIS
        output += "### 📋 WHOIS IP\n"
        try:
            w = IPWhois(ip_address)
            result = w.lookup_rdap()

            if result:
                if result.get("asn"):
                    output += f"• ASN: {result['asn']}\n"
                if result.get("asn_description"):
                    output += f"• Descripción ASN: {result['asn_description']}\n"
                if result.get("asn_country_code"):
                    output += f"• País ASN: {result['asn_country_code']}\n"
                if result.get("network", {}).get("name"):
                    output += f"• Red: {result['network']['name']}\n"
                if result.get("objects"):
                    for obj_key, obj_data in result["objects"].items():
                        if isinstance(obj_data, dict):
                            contact = obj_data.get("contact", {})
                            if contact.get("name"):
                                output += f"• Propietario: {contact['name']}\n"
                                break
        except Exception as e:
            output += f"• Error WHOIS: {e}\n"

        # Geolocation (free API)
        output += "\n### 📍 Geolocalización\n"
        try:
            geo_url = f"http://ip-api.com/json/{ip_address}"
            if not is_safe_url(geo_url):
                output += "• Geolocalización bloqueada por seguridad\n"
            else:
                resp = requests.get(geo_url, timeout=5)
                if resp.status_code == 200:
                    geo = resp.json()
                    if geo.get("status") == "success":
                        output += f"• País: {geo.get('country', 'N/A')}\n"
                        output += f"• Región: {geo.get('regionName', 'N/A')}\n"
                        output += f"• Ciudad: {geo.get('city', 'N/A')}\n"
                        output += f"• ISP: {geo.get('isp', 'N/A')}\n"
                        output += f"• Organización: {geo.get('org', 'N/A')}\n"
                        output += f"• ASN: {geo.get('as', 'N/A')}\n"
        except Exception:
            output += "• Geolocalización no disponible\n"

        # Reverse DNS
        output += "\n### 🔍 Reverse DNS\n"
        try:
            import socket
            hostname = socket.gethostbyaddr(ip_address)
            output += f"• Hostname: {hostname[0]}\n"
            if hostname[1]:
                output += f"• Aliases: {', '.join(hostname[1])}\n"
        except Exception:
            output += "• Sin reverse DNS\n"

        # Check common ports
        output += "\n### 🔌 Puertos Comunes\n"
        common_ports = [22, 80, 443, 8080, 8443]
        open_ports = []

        for port in common_ports:
            try:
                import socket
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((ip_address, port))
                if result == 0:
                    open_ports.append(port)
                    output += f"• ✅ Puerto {port}: Abierto\n"
                sock.close()
            except Exception:
                pass

        if not open_ports:
            output += "• No se detectaron puertos abiertos (limitado por timeout)\n"

        log_operation("osint_ip", {"ip": ip_address}, "OK")
        return output

    except Exception as e:
        return f"Error en OSINT IP: {e}"



def _osint_person_handler(name: str, email: str = None, location: str = None) -> str:
    """Search for a person across platforms by name."""
    try:
        output = f"👤 **Búsqueda OSINT: {name}**\n\n"

        # Generate username variations
        name_parts = name.lower().split()
        username_variations = set()

        if len(name_parts) >= 2:
            first = name_parts[0]
            last = name_parts[-1]

            # Common username patterns
            username_variations.add(f"{first}{last}")
            username_variations.add(f"{first}.{last}")
            username_variations.add(f"{first}_{last}")
            username_variations.add(f"{first[0]}{last}")
            username_variations.add(f"{first}{last[0]}")
            username_variations.add(f"{last}{first}")
            username_variations.add(f"{last}.{first}")

            # With numbers
            for i in range(10):
                username_variations.add(f"{first}{last}{i}")
                username_variations.add(f"{first}.{last}{i}")

        # Add email username if provided
        if email:
            email_user = email.split("@")[0]
            username_variations.add(email_user)

        output += f"🔍 Buscando variaciones de username: {len(username_variations)}\n\n"

        # Search each variation (limit to avoid timeout)
        found_accounts = []
        search_limit = min(len(username_variations), 5)

        for i, username in enumerate(list(username_variations)[:search_limit]):
            try:
                # Use simple HTTP check for each platform
                platforms = {
                    "GitHub": f"https://github.com/{username}",
                    "Twitter": f"https://twitter.com/{username}",
                    "Instagram": f"https://www.instagram.com/{username}/",
                    "Reddit": f"https://www.reddit.com/user/{username}",
                    "LinkedIn": f"https://www.linkedin.com/in/{username}",
                }

                for platform, url in platforms.items():
                    try:
                        import requests
                        resp = requests.get(url, timeout=5, allow_redirects=False,
                                          headers={"User-Agent": "Mozilla/5.0"})
                        if resp.status_code == 200:
                            found_accounts.append({
                                "platform": platform,
                                "url": url,
                                "username": username
                            })
                    except Exception:
                        pass

            except Exception:
                pass

        if found_accounts:
            output += f"📊 **Cuentas encontradas:** {len(found_accounts)}\n\n"
            for acc in found_accounts:
                output += f"• {acc['platform']}: [{acc['username']}]({acc['url']})\n"
        else:
            output += "No se encontraron cuentas con las variaciones buscadas\n"
            output += "💡 Prueba con la herramienta `osint_username` para una búsqueda más profunda\n"

        # Search location if provided
        if location:
            output += f"\n📍 **Ubicación:** {location}\n"
            output += "ℹ️ La información de ubicación es pública y puede requerir verificación\n"

        log_operation("osint_person", {"name": name, "email": email}, f"{len(found_accounts)} accounts")
        return output

    except Exception as e:
        return f"Error en OSINT persona: {e}"


# ── Audit & Observability Tools ─────────────────────────────

HANDLERS = {
    "osint_username": _osint_username_handler,
    "osint_email": _osint_email_handler,
    "osint_domain": _osint_domain_handler,
    "osint_ip": _osint_ip_handler,
    "osint_person": _osint_person_handler,
}
