"""Network diagnostics: ping, ports, speed, ARP, subnet scan, port scan, DNS, SSL, WHOIS."""

import os
import subprocess
import socket
import concurrent.futures



TOOLS = [
    {
        "name": "network_ping",
        "description": "Hace ping a un host para verificar conectividad.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o IP a hacer ping."
                },
                "count": {
                    "type": "integer",
                    "description": "Numero de paquetes. Default: 4."
                }
            },
            "required": ["host"]
        }
    },
    {
        "name": "network_ports",
        "description": "Muestra puertos abiertos en el sistema.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filter": {
                    "type": "string",
                    "description": "Filtrar por estado (LISTEN, ESTABLISHED, etc.)."
                }
            },
            "required": []
        }
    },
    {
        "name": "network_speed",
        "description": "Mide la velocidad de internet (upload/download).",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "network_info",
        "description": "Muestra informacion de red: interfaces, IPs, gateway, DNS.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "network_arp_table",
        "description": "Muestra la tabla de resolucion ARP (Capa 2/3) con dispositivos vecinos descubiertos e interfaces sin root.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "network_scan_subnet",
        "description": "Escanea concurrentemente un segmento o subred de IPs sin requerir root para encontrar dispositivos activos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "subnet_base": {
                    "type": "string",
                    "description": "Base de subred (ej: '172.31.0' o '192.168.1')."
                },
                "start_ip": {
                    "type": "integer",
                    "description": "IP inicial del rango (1-254). Default: 1."
                },
                "end_ip": {
                    "type": "integer",
                    "description": "IP final del rango (1-254). Default: 50."
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Timeout por sondeo en ms. Default: 150."
                }
            },
            "required": ["subnet_base"]
        }
    },
    {
        "name": "network_port_scan",
        "description": "Escanea puertos TCP en un objetivo para auditoria de servicios (Capa 4 Transporte) sin requerir root.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "target_ip": {
                    "type": "string",
                    "description": "IP o host objetivo a escanear."
                },
                "ports": {
                    "type": "string",
                    "description": "Lista separada por comas de puertos a escanear (ej: '22,80,443,8080')."
                },
                "timeout_ms": {
                    "type": "integer",
                    "description": "Timeout por puerto en ms. Default: 250."
                }
            },
            "required": ["target_ip"]
        }
    },
    {
        "name": "network_interfaces_detailed",
        "description": "Auditoria exhaustiva de Capa 2/3: interfaces, MTU, estado, MACs, trafico RX/TX y servidores DNS.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "dns_lookup",
        "description": "Consulta DNS (A, AAAA, MX, TXT, NS, CNAME).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Dominio a consultar."
                },
                "record_type": {
                    "type": "string",
                    "enum": ["A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA", "ALL"],
                    "description": "Tipo de registro.",
                    "default": "ALL"
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "ssl_check",
        "description": "Verifica certificado SSL de un dominio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Dominio a verificar."
                }
            },
            "required": ["domain"]
        }
    },
    {
        "name": "whois_lookup",
        "description": "Consulta WHOIS de un dominio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Dominio a consultar."
                }
            },
            "required": ["domain"]
        }
    },
]

# ── Handlers ───────────────────────────────────────────────


def _network_ping(args):
    host = args.get("host", "")
    count = args.get("count", 4)
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), host],
            capture_output=True, text=True, timeout=30
        )

        if result.returncode != 0:
            return f"No se pudo hacer ping a {host}"

        lines = result.stdout.strip().split("\n")
        stats_line = [l for l in lines if "avg" in l]
        if stats_line:
            return f"Ping {host}: {stats_line[0]}"
        return f"Ping {host}: OK"

    except subprocess.TimeoutExpired:
        return f"Timeout haciendo ping a {host}"
    except Exception as e:
        return f"Error haciendo ping: {e}"


def _network_ports(args):
    filter_state = args.get("filter", "LISTEN")
    try:
        result = subprocess.run(
            ["ss", "-tlnp"],
            capture_output=True, text=True, timeout=10
        )

        if result.returncode != 0:
            return "Error obteniendo puertos"

        lines = result.stdout.strip().split("\n")
        filtered = [l for l in lines if filter_state.upper() in l.upper()]

        if not filtered:
            return f"No hay puertos con estado: {filter_state}"

        return f"Puertos ({filter_state}):\n" + "\n".join(filtered[:20])

    except Exception as e:
        return f"Error obteniendo puertos: {e}"


def _network_speed(args):
    try:
        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{speed_download}", "https://speed.cloudflare.com/__down?bytes=1000000"],
            capture_output=True, text=True, timeout=30
        )

        speed_bps = float(result.stdout) if result.stdout else 0
        speed_mbps = speed_bps / 1024 / 1024

        return f"Velocidad de descarga: {speed_mbps:.2f} MB/s"

    except Exception as e:
        return f"Error midiendo velocidad: {e}"


def _network_info(args):
    try:
        info = []

        result = subprocess.run(["ip", "-4", "addr", "show"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            for line in result.stdout.split("\n"):
                if "inet " in line and "127.0.0.1" not in line:
                    parts = line.split()
                    for i, p in enumerate(parts):
                        if p == "inet":
                            info.append(f"IP: {parts[i+1]}")
                            break

        result = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            parts = result.stdout.split()
            for i, p in enumerate(parts):
                if p == "via":
                    info.append(f"Gateway: {parts[i+1]}")
                    break

        try:
            with open("/etc/resolv.conf") as f:
                for line in f:
                    if line.startswith("nameserver"):
                        info.append(f"DNS: {line.split()[1]}")
        except:
            pass

        return "Red:\n" + "\n".join(f"  {i}" for i in info) if info else "No se pudo obtener info de red"

    except Exception as e:
        return f"Error obteniendo info de red: {e}"


def _network_arp_table(args):
    try:
        if not os.path.exists("/proc/net/arp"):
            return "/proc/net/arp no disponible en este sistema."
        with open("/proc/net/arp") as f:
            lines = f.readlines()
        if len(lines) <= 1:
            return "Tabla ARP vacia."
        
        entries = []
        for line in lines[1:]:
            parts = line.split()
            if len(parts) >= 6:
                ip, hw_type, flags, mac, mask, dev = parts[:6]
                if mac != "00:00:00:00:00:00":
                    entries.append(f"IP: `{ip:<15}` | MAC: `{mac}` | Interfaz: `{dev}`")
        
        return "Tabla ARP del Sistema (Dispositivos Vecinos Descubiertos):\n\n" + ("\n".join(entries) if entries else "No se detectaron vecinos con MAC valida.")
    except Exception as e:
        return f"Error leyendo tabla ARP: {e}"


def _network_scan_subnet(args):
    subnet_base = args.get("subnet_base", "172.31.0")
    start_ip = max(1, min(args.get("start_ip", 1), 254))
    end_ip = max(start_ip, min(args.get("end_ip", 50), 254))
    timeout_ms = args.get("timeout_ms", 150)
    timeout = timeout_ms / 1000.0

    def probe_host(target_ip):
        try:
            r = subprocess.run(["ping", "-c", "1", "-W", "1", target_ip], capture_output=True, timeout=1.2)
            if r.returncode == 0:
                rtt = "OK"
                for l in r.stdout.decode().splitlines():
                    if "time=" in l:
                        rtt = l.split("time=")[1].split()[0] + "ms"
                return {"ip": target_ip, "status": "active", "method": "ICMP", "rtt": rtt}
        except Exception:
            pass

        for port in [80, 443, 22, 53, 445, 8080, 3000, 8000]:
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                if s.connect_ex((target_ip, port)) == 0:
                    s.close()
                    return {"ip": target_ip, "status": "active", "method": f"TCP:{port}", "rtt": f"<{timeout_ms}ms"}
                s.close()
            except Exception:
                pass

        return None

    active_hosts = []
    ips_to_scan = [f"{subnet_base}.{i}" for i in range(start_ip, end_ip + 1)]
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(50, len(ips_to_scan))) as executor:
        results = executor.map(probe_host, ips_to_scan)
        for res in results:
            if res:
                active_hosts.append(res)

    if not active_hosts:
        return f"Escaneo de Red ({subnet_base}.{start_ip} - {end_ip}):\nNo se detectaron hosts respondiendo en este rango (podrian tener ICMP/TCP filtrado por firewall de red)."

    output = [f"Escaneo de Subred ({subnet_base}.{start_ip} - {end_ip}) - {len(active_hosts)} Hosts Activos:\n"]
    for h in active_hosts:
        output.append(f"  `{h['ip']:<15}` - Respuesta via **{h['method']}** (Latencia: {h['rtt']})")
    
    return "\n".join(output)


def _network_port_scan(args):
    target_ip = args.get("target_ip", "")
    ports_str = args.get("ports", "21,22,23,25,53,80,110,139,443,445,3000,3306,5432,8000,8080,9090")
    timeout_ms = args.get("timeout_ms", 250)

    try:
        port_list = [int(p.strip()) for p in ports_str.split(",") if p.strip().isdigit()]
    except Exception:
        port_list = [22, 80, 443, 8080, 9090]

    timeout = timeout_ms / 1000.0
    common_services = {
        21: "FTP", 22: "SSH", 23: "Telnet", 25: "SMTP", 53: "DNS",
        80: "HTTP", 110: "POP3", 139: "NetBIOS", 443: "HTTPS", 445: "SMB",
        3000: "Dev Server (Node/React)", 3306: "MySQL", 5432: "PostgreSQL",
        8000: "HTTP Alt / Django", 8080: "HTTP Proxy / Tomcat", 9090: "llama.cpp / Gemma 4"
    }

    def check_port(p):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(timeout)
            code = s.connect_ex((target_ip, p))
            s.close()
            if code == 0:
                service = common_services.get(p, "Desconocido")
                return {"port": p, "state": "OPEN", "service": service}
        except Exception:
            pass
        return None

    open_ports = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        for res in executor.map(check_port, port_list):
            if res:
                open_ports.append(res)

    if not open_ports:
        return f"Escaneo de Puertos en `{target_ip}`:\nTodos los puertos analizados ({len(port_list)} puertos) estan cerrados o filtrados por firewall."

    lines = [f"Puertos Abiertos en `{target_ip}` ({len(open_ports)}/{len(port_list)} detectados):\n"]
    for item in sorted(open_ports, key=lambda x: x["port"]):
        lines.append(f"  Puerto **{item['port']:<5}/TCP** - ABIERTO ({item['service']})")
    
    return "\n".join(lines)


def _network_interfaces_detailed(args):
    try:
        report = []
        net_dir = "/sys/class/net"
        if os.path.exists(net_dir):
            for iface in sorted(os.listdir(net_dir)):
                iface_path = os.path.join(net_dir, iface)
                if not os.path.isdir(iface_path):
                    continue
                
                operstate = "unknown"
                try:
                    with open(os.path.join(iface_path, "operstate")) as f:
                        operstate = f.read().strip()
                except Exception:
                    pass
                
                mac = "N/A"
                try:
                    with open(os.path.join(iface_path, "address")) as f:
                        mac = f.read().strip()
                except Exception:
                    pass

                rx_bytes = 0
                tx_bytes = 0
                try:
                    with open(os.path.join(iface_path, "statistics/rx_bytes")) as f:
                        rx_bytes = int(f.read().strip())
                    with open(os.path.join(iface_path, "statistics/tx_bytes")) as f:
                        tx_bytes = int(f.read().strip())
                except Exception:
                    pass

                status_icon = "UP" if operstate == "up" else "DOWN"
                rx_mb = rx_bytes / (1024 * 1024)
                tx_mb = tx_bytes / (1024 * 1024)
                
                report.append(f"{status_icon} **`{iface}`** ({operstate.upper()}):\n   MAC: `{mac}`\n   Trafico: RX: `{rx_mb:.1f} MB` | TX: `{tx_mb:.1f} MB`")

        route_proc = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True)
        default_route = route_proc.stdout.strip() or "No default route"

        dns_servers = []
        try:
            with open("/etc/resolv.conf") as f:
                for l in f:
                    if l.startswith("nameserver"):
                        dns_servers.append(l.split()[1])
        except Exception:
            pass

        return (
            "Auditoria de Interfaces y Capa de Enlace (L2/L3):\n\n"
            + "\n\n".join(report)
            + f"\n\nPuerta de Enlace (Default Route):\n`{default_route}`\n"
            + f"Servidores DNS: `{', '.join(dns_servers) if dns_servers else 'N/A'}`"
        )
    except Exception as e:
        return f"Error en auditoria de interfaces: {e}"


def _dns_lookup(args):
    domain = args.get("domain", "")
    record_type = args.get("record_type", "ALL")
    try:
        import dns.resolver
        
        record_types = ["A", "AAAA", "MX", "TXT", "NS", "CNAME", "SOA"]
        if record_type != "ALL":
            record_types = [record_type]
        
        output = f"DNS para {domain}:\n\n"
        
        for rtype in record_types:
            try:
                answers = dns.resolver.resolve(domain, rtype)
                output += f"{rtype}:\n"
                for rdata in answers:
                    output += f"  - {rdata}\n"
                output += "\n"
            except dns.resolver.NoAnswer:
                pass
            except dns.resolver.NXDOMAIN:
                return f"Error: Dominio {domain} no existe"
            except Exception:
                pass
        
        return output if output.strip() != f"DNS para {domain}:" else "No se encontraron registros"
    
    except ImportError:
        return "Error: dnspython no instalado"
    except Exception as e:
        return f"Error DNS: {e}"


def _ssl_check(args):
    domain = args.get("domain", "")
    try:
        import ssl
        from datetime import datetime
        
        context = ssl.create_default_context()
        
        with socket.create_connection((domain, 443), timeout=10) as sock:
            with context.wrap_socket(sock, server_hostname=domain) as ssock:
                cert = ssock.getpeercert()
        
        not_before = datetime.strptime(cert['notBefore'], '%b %d %H:%M:%S %Y %Z')
        not_after = datetime.strptime(cert['notAfter'], '%b %d %H:%M:%S %Y %Z')
        days_left = (not_after - datetime.now()).days
        
        output = f"SSL para {domain}:\n\n"
        output += f"  Emisor: {dict(x[0] for x in cert['issuer']).get('commonName', 'N/A')}\n"
        output += f"  Valido desde: {not_before.strftime('%Y-%m-%d')}\n"
        output += f"  Valido hasta: {not_after.strftime('%Y-%m-%d')}\n"
        output += f"  Dias restantes: {days_left}\n"
        output += f"  Dominios: {', '.join(cert.get('subjectAltName', [('*', )])[0][1] if cert.get('subjectAltName') else [domain])}\n"
        
        if days_left < 30:
            output += f"\nCertificado expira en {days_left} dias!"
        else:
            output += f"\nCertificado valido"
        
        return output
    
    except Exception as e:
        return f"Error verificando SSL: {e}"


def _whois_lookup(args):
    domain = args.get("domain", "")
    try:
        import whois
        
        w = whois.whois(domain)
        
        output = f"WHOIS para {domain}:\n\n"
        
        if w.domain_name:
            output += f"  Dominio: {w.domain_name}\n"
        if w.registrar:
            output += f"  Registrar: {w.registrar}\n"
        if w.creation_date:
            output += f"  Creado: {w.creation_date}\n"
        if w.expiration_date:
            output += f"  Expira: {w.expiration_date}\n"
        if w.name_servers:
            output += f"  Name Servers: {', '.join(w.name_servers[:3])}\n"
        if w.org:
            output += f"  Organizacion: {w.org}\n"
        if w.country:
            output += f"  Pais: {w.country}\n"
        
        return output
    
    except ImportError:
        return "Error: python-whois no instalado"
    except Exception as e:
        return f"Error WHOIS: {e}"


HANDLERS = {
    "network_ping": _network_ping,
    "network_ports": _network_ports,
    "network_speed": _network_speed,
    "network_info": _network_info,
    "network_arp_table": _network_arp_table,
    "network_scan_subnet": _network_scan_subnet,
    "network_port_scan": _network_port_scan,
    "network_interfaces_detailed": _network_interfaces_detailed,
    "dns_lookup": _dns_lookup,
    "ssl_check": _ssl_check,
    "whois_lookup": _whois_lookup,
}
