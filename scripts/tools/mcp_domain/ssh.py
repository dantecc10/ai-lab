"""SSH connection and file transfer tools"""

import os
import subprocess

from mcp_common.logging import log_operation

TOOLS = [
    {
        "name": "ssh_connect",
        "description": "Ejecuta un comando en un servidor remoto vía SSH.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH (ej: vps, 192.168.1.100)."
                },
                "command": {
                    "type": "string",
                    "description": "Comando a ejecutar remotamente."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH (default: darkseid)."
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos.",
                    "default": 30
                }
            },
            "required": ["host", "command"]
        }
    },
    {
        "name": "ssh_copy",
        "description": "Copia archivos al servidor remoto vía SCP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH."
                },
                "local_path": {
                    "type": "string",
                    "description": "Ruta local del archivo."
                },
                "remote_path": {
                    "type": "string",
                    "description": "Ruta remota de destino."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH."
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                }
            },
            "required": ["host", "local_path", "remote_path"]
        }
    },
    {
        "name": "ssh_fetch",
        "description": "Descarga archivos del servidor remoto vía SCP.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH."
                },
                "remote_path": {
                    "type": "string",
                    "description": "Ruta remota del archivo."
                },
                "local_path": {
                    "type": "string",
                    "description": "Ruta local de destino."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH."
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                }
            },
            "required": ["host", "remote_path", "local_path"]
        }
    },
    {
        "name": "ssh_sync",
        "description": "Sincroniza directorios locales con remoto vía rsync.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH."
                },
                "local_path": {
                    "type": "string",
                    "description": "Ruta local."
                },
                "remote_path": {
                    "type": "string",
                    "description": "Ruta remota."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH."
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                },
                "delete": {
                    "type": "boolean",
                    "description": "Eliminar archivos en remoto que no existen local.",
                    "default": False
                },
                "exclude": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Patrones a excluir."
                }
            },
            "required": ["host", "local_path", "remote_path"]
        }
    },
    {
        "name": "ssh_tunnel",
        "description": "Crea un túnel SSH con autossh para port forwarding.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host remoto."
                },
                "local_port": {
                    "type": "integer",
                    "description": "Puerto local."
                },
                "remote_port": {
                    "type": "integer",
                    "description": "Puerto remoto."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH."
                },
                "ssh_port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                },
                "background": {
                    "type": "boolean",
                    "description": "Ejecutar en segundo plano.",
                    "default": True
                }
            },
            "required": ["host", "local_port", "remote_port"]
        }
    },
    {
        "name": "ssh_list_hosts",
        "description": "Lista hosts configurados en ~/.ssh/config.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "ssh_add_host",
        "description": "Agrega un host a ~/.ssh/config.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hostname": {
                    "type": "string",
                    "description": "Alias del host (ej: vps)."
                },
                "host": {
                    "type": "string",
                    "description": "IP o dominio del servidor."
                },
                "user": {
                    "type": "string",
                    "description": "Usuario SSH.",
                    "default": "darkseid"
                },
                "port": {
                    "type": "integer",
                    "description": "Puerto SSH.",
                    "default": 22
                },
                "identity_file": {
                    "type": "string",
                    "description": "Ruta de la clave SSH (opcional)."
                }
            },
            "required": ["hostname", "host"]
        }
    },
    {
        "name": "ssh_status",
        "description": "Verifica estado de un servidor remoto (ping + SSH).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Host o alias SSH."
                }
            },
            "required": ["host"]
        }
    },
]

def _parse_ssh_config() -> dict:
    """Parse ~/.ssh/config into a dict of host aliases."""
    ssh_config_path = os.path.expanduser("~/.ssh/config")
    hosts = {}
    
    if not os.path.exists(ssh_config_path):
        return hosts
    
    current_host = None
    with open(ssh_config_path, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            
            if line.lower().startswith("host "):
                current_host = line.split(None, 1)[1]
                hosts[current_host] = {"hostname": current_host, "user": "darkseid", "port": 22}
            elif current_host:
                parts = line.split(None, 1)
                if len(parts) == 2:
                    key = parts[0].lower()
                    value = parts[1]
                    if key == "hostname":
                        hosts[current_host]["hostname"] = value
                    elif key == "user":
                        hosts[current_host]["user"] = value
                    elif key == "port":
                        hosts[current_host]["port"] = int(value)
                    elif key == "identityfile":
                        hosts[current_host]["identity_file"] = value
    
    return hosts



def _resolve_host(host: str) -> dict:
    """Resolve host alias or return direct connection info."""
    hosts = _parse_ssh_config()
    
    if host in hosts:
        return hosts[host]
    
    # Direct IP/hostname
    return {"hostname": host, "user": "darkseid", "port": 22}



# ── Handlers ───────────────────────────────────────────────
def _ssh_connect_handler(host: str, command: str, user: str = None, port: int = 22, timeout: int = 30) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_port = port or host_info.get("port", 22)
        ssh_hostname = host_info.get("hostname", host)
        
        ssh_cmd = ["ssh", "-o", "StrictHostKeyChecking=no", "-p", str(ssh_port), f"{ssh_user}@{ssh_hostname}", command]
        
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        output = result.stdout
        if result.stderr:
            output += f"\n[stderr] {result.stderr}"
        
        log_operation("ssh_connect", {"host": host, "command": command}, f"exit:{result.returncode}")
        return f"[exit:{result.returncode}] {output.strip()}"
    
    except subprocess.TimeoutExpired:
        return f"Error: Timeout ({timeout}s) conectando a {host}"
    except Exception as e:
        return f"Error SSH: {e}"



def _ssh_copy_handler(host: str, local_path: str, remote_path: str, user: str = None, port: int = 22) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_port = port or host_info.get("port", 22)
        ssh_hostname = host_info.get("hostname", host)
        
        local_path = os.path.expanduser(local_path)
        
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-P", str(ssh_port), local_path, f"{ssh_user}@{ssh_hostname}:{remote_path}"],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            log_operation("ssh_copy", {"host": host, "local": local_path, "remote": remote_path}, "OK")
            return f"Archivo copiado a {host}:{remote_path}"
        else:
            return f"Error SCP: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"



def _ssh_fetch_handler(host: str, remote_path: str, local_path: str, user: str = None, port: int = 22) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_port = port or host_info.get("port", 22)
        ssh_hostname = host_info.get("hostname", host)
        
        local_path = os.path.expanduser(local_path)
        
        result = subprocess.run(
            ["scp", "-o", "StrictHostKeyChecking=no", "-P", str(ssh_port), f"{ssh_user}@{ssh_hostname}:{remote_path}", local_path],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            log_operation("ssh_fetch", {"host": host, "remote": remote_path, "local": local_path}, "OK")
            return f"Archivo descargado a {local_path}"
        else:
            return f"Error SCP: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"



def _ssh_sync_handler(host: str, local_path: str, remote_path: str, user: str = None, port: int = 22, delete: bool = False, exclude: list = None) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_port = port or host_info.get("port", 22)
        ssh_hostname = host_info.get("hostname", host)
        
        local_path = os.path.expanduser(local_path)
        
        rsync_cmd = ["rsync", "-avz", "-e", f"ssh -o StrictHostKeyChecking=no -p {ssh_port}"]
        
        if delete:
            rsync_cmd.append("--delete")
        
        if exclude:
            for pattern in exclude:
                rsync_cmd.extend(["--exclude", pattern])
        
        rsync_cmd.extend([f"{local_path}/", f"{ssh_user}@{ssh_hostname}:{remote_path}/"])
        
        result = subprocess.run(
            rsync_cmd,
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            log_operation("ssh_sync", {"host": host, "local": local_path, "remote": remote_path}, "OK")
            return f"Sincronizado: {local_path} → {host}:{remote_path}"
        else:
            return f"Error rsync: {result.stderr}"
    
    except Exception as e:
        return f"Error: {e}"



def _ssh_tunnel_handler(host: str, local_port: int, remote_port: int, user: str = None, ssh_port: int = 22, background: bool = True) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_user = user or host_info.get("user", "darkseid")
        ssh_hostname = host_info.get("hostname", host)
        
        ssh_args = [
            "ssh", "-o", "StrictHostKeyChecking=no",
            "-p", str(ssh_port),
            "-L", f"{local_port}:localhost:{remote_port}",
            f"{ssh_user}@{ssh_hostname}"
        ]
        
        if background:
            autossh_cmd = ["autossh", "-M", "0", "-f", "-N"] + ssh_args
            result = subprocess.run(
                autossh_cmd,
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                log_operation("ssh_tunnel", {"host": host, "local_port": local_port, "remote_port": remote_port}, "OK")
                return f"Túnel creado: localhost:{local_port} → {host}:{remote_port}"
            else:
                return f"Error túnel: {result.stderr}"
        else:
            subprocess.run(ssh_args, timeout=30)
            return "Túnel cerrado"
    
    except Exception as e:
        return f"Error: {e}"



def _ssh_list_hosts_handler() -> str:
    try:
        hosts = _parse_ssh_config()
        
        if not hosts:
            return "No hay hosts configurados en ~/.ssh/config"
        
        result = "Hosts SSH configurados:\n"
        for name, info in hosts.items():
            result += f"  {name}: {info.get('user', 'darkseid')}@{info.get('hostname', '?')}:{info.get('port', 22)}\n"
        
        return result
    
    except Exception as e:
        return f"Error: {e}"



def _ssh_add_host_handler(hostname: str, host: str, user: str = "darkseid", port: int = 22, identity_file: str = None) -> str:
    try:
        ssh_config_path = os.path.expanduser("~/.ssh/config")
        
        # Check if host already exists
        hosts = _parse_ssh_config()
        if hostname in hosts:
            return f"Error: Host '{hostname}' ya existe. Usa ssh_config para editarlo."
        
        # Build config entry
        entry = f"\nHost {hostname}\n"
        entry += f"    HostName {host}\n"
        entry += f"    User {user}\n"
        entry += f"    Port {port}\n"
        if identity_file:
            entry += f"    IdentityFile {identity_file}\n"
        entry += "    StrictHostKeyChecking no\n"
        
        # Append to config
        with open(ssh_config_path, "a") as f:
            f.write(entry)
        
        log_operation("ssh_add_host", {"hostname": hostname, "host": host}, "OK")
        return f"Host '{hostname}' agregado a ~/.ssh/config"
    
    except Exception as e:
        return f"Error: {e}"



def _ssh_status_handler(host: str) -> str:
    try:
        host_info = _resolve_host(host)
        
        ssh_hostname = host_info.get("hostname", host)
        ssh_port = host_info.get("port", 22)
        
        # Ping
        ping_result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", ssh_hostname],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        ping_ok = ping_result.returncode == 0
        
        # SSH port check
        ssh_result = subprocess.run(
            ["nc", "-z", "-w", "2", ssh_hostname, str(ssh_port)],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        ssh_ok = ssh_result.returncode == 0
        
        status = f"Host: {ssh_hostname}:{ssh_port}\n"
        status += f"Ping: {'OK' if ping_ok else 'FALLA'}\n"
        status += f"SSH:  {'OK' if ssh_ok else 'FALLA'}\n"
        
        if ping_ok and ssh_ok:
            status += "Estado: ONLINE"
        elif ping_ok:
            status += "Estado: SSH bloqueado"
        else:
            status += "Estado: OFFLINE"
        
        return status
    
    except Exception as e:
        return f"Error: {e}"


# ── Web & Internet Implementations ─────────────────────────

HANDLERS = {
    "ssh_connect": _ssh_connect_handler,
    "ssh_copy": _ssh_copy_handler,
    "ssh_fetch": _ssh_fetch_handler,
    "ssh_sync": _ssh_sync_handler,
    "ssh_tunnel": _ssh_tunnel_handler,
    "ssh_list_hosts": _ssh_list_hosts_handler,
    "ssh_add_host": _ssh_add_host_handler,
    "ssh_status": _ssh_status_handler,
}
