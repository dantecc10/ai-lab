"""Filesystem domain: navigation, file I/O, search, command execution."""

import os
import glob
import json
import subprocess
from datetime import datetime

from mcp_common.paths import HOME, BASE_DIR, MAX_OUTPUT_LINES, MAX_FILE_SIZE, COMMAND_TIMEOUT, safe_path, format_size, format_permissions
from mcp_common.security import is_blocked_command, is_destructive_command
from mcp_common.logging import log_operation

TOOLS = [
    {
        "name": "list_directory",
        "description": "Lista archivos y carpetas en un directorio. Retorna nombres, tamaños y tipo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del directorio. Default: home directory."
                },
                "show_hidden": {
                    "type": "boolean",
                    "description": "Incluir archivos ocultos (que empiezan con .). Default: false."
                }
            },
            "required": []
        }
    },
    {
        "name": "file_info",
        "description": "Muestra metadata detallada de un archivo o carpeta: tamaño, permisos, fechas, tipo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo o carpeta."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "search_files",
        "description": "Busca archivos por nombre usando patrón glob (ej: '*.py', '**/*.txt').",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Patrón de búsqueda glob."
                },
                "path": {
                    "type": "string",
                    "description": "Directorio base para buscar. Default: home."
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "read_file",
        "description": "Lee el contenido de un archivo de texto. Soporta lectura por rango de líneas (start_line, end_line) para máxima eficiencia sin cargar todo el archivo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a leer."
                },
                "start_line": {
                    "type": "integer",
                    "description": "Línea inicial a leer (1-indexed). Default: 1."
                },
                "end_line": {
                    "type": "integer",
                    "description": "Línea final a leer (inclusive). Si no se especifica, lee hasta max_lines."
                },
                "max_lines": {
                    "type": "integer",
                    "description": "Máximo de líneas a leer desde start_line. Default: 200."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Crea un archivo NUEVO o sobreescribe COMPLETAMENTE uno existente. Para agregar al final usar append_to_file, para modificar secciones usar replace_file_content.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a escribir."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido completo del nuevo archivo."
                },
                "append": {
                    "type": "boolean",
                    "description": "Si es true, agrega al final. Preferir append_to_file."
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "append_to_file",
        "description": "AGREGA contenido directamente al FINAL de un archivo existente sin reescribir el previo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo existente al que se añadirá texto al final."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido que se anexará al final del archivo."
                }
            },
            "required": ["path", "content"]
        }
    },
    {
        "name": "replace_file_content",
        "description": "REEMPLAZA quirúrgicamente un bloque de texto exacto por nuevo texto dentro de un archivo existente.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo existente a modificar."
                },
                "target_content": {
                    "type": "string",
                    "description": "Texto exacto preexistente que se desea reemplazar."
                },
                "replacement_content": {
                    "type": "string",
                    "description": "Nuevo texto con el que se reemplazará target_content."
                }
            },
            "required": ["path", "target_content", "replacement_content"]
        }
    },
    {
        "name": "compact_context",
        "description": "Compacta y sintetiza un historial conversacional o documento extenso, reduciendo tokens al 15-20% preservando decisiones clave.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Texto o fragmentos de conversación que se desean compactar."
                }
            },
            "required": ["content"]
        }
    },
    {
        "name": "run_command",
        "description": "Ejecuta un comando del sistema y retorna su salida. Comandos destructivos requieren confirmación.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Comando a ejecutar (ej: 'ls -la', 'df -h', 'free -m')."
                },
                "confirm": {
                    "type": "boolean",
                    "description": "Confirmar ejecución de comandos destructivos. Default: false."
                }
            },
            "required": ["command"]
        }
    },
    {
        "name": "run_python_script",
        "description": "Ejecuta un script Python aislado y retorna stdout/stderr.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "script": {
                    "type": "string",
                    "description": "Código Python a ejecutar (una línea o bloque)."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos. Default: 30."
                }
            },
            "required": ["script"]
        }
    },
    {
        "name": "file_compress",
        "description": "Comprime archivos o carpetas en .tar.gz o .zip.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Ruta del archivo o carpeta a comprimir."
                },
                "format": {
                    "type": "string",
                    "enum": ["tar.gz", "zip"],
                    "description": "Formato de compresión. Default: tar.gz."
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "file_extract",
        "description": "Extrae archivos comprimidos (.tar.gz, .zip, .tar.bz2).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "source": {
                    "type": "string",
                    "description": "Ruta del archivo a extraer."
                },
                "destination": {
                    "type": "string",
                    "description": "Directorio destino. Default: directorio actual."
                }
            },
            "required": ["source"]
        }
    },
    {
        "name": "file_permissions",
        "description": "Cambia permisos de archivos o carpetas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo."
                },
                "mode": {
                    "type": "string",
                    "description": "Permisos en formato octal (ej: '755') o simbólico (ej: '+x')."
                }
            },
            "required": ["path", "mode"]
        }
    },
]


# ── Handlers ───────────────────────────────────────────────

def _list_directory(args):
    path = args.get("path")
    show_hidden = args.get("show_hidden", False)
    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: Directorio no existe: {target}"
    if not os.path.isdir(target):
        return f"Error: No es un directorio: {target}"

    entries = []
    try:
        for name in sorted(os.listdir(target)):
            if not show_hidden and name.startswith("."):
                continue
            full_path = os.path.join(target, name)
            try:
                st = os.lstat(full_path)
                is_dir = os.path.isdir(full_path)
                size = st.st_size if not is_dir else 0
                entries.append({
                    "name": name + ("/" if is_dir else ""),
                    "type": "dir" if is_dir else "file",
                    "size": format_size(size) if not is_dir else "-"
                })
            except OSError:
                entries.append({"name": name, "type": "unknown", "size": "?"})
    except PermissionError:
        return f"Error: Sin permisos para leer: {target}"

    if not entries:
        return f"Directorio vacío: {target}"

    lines = [f"📁 {target} ({len(entries)} elementos)\n"]
    for e in entries:
        icon = "📁" if e["type"] == "dir" else "📄"
        lines.append(f"  {icon} {e['name']:40s} {e['size']}")

    return "\n".join(lines)


def _file_info(args):
    path = args["path"]
    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: No existe: {target}"

    try:
        st = os.lstat(target)

        is_dir = os.path.isdir(target)
        is_link = os.path.islink(target)
        size = st.st_size
        perms = format_permissions(st.st_mode)
        modified = datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        created = datetime.fromtimestamp(st.st_ctime).strftime("%Y-%m-%d %H:%M:%S")

        file_type = "Directorio" if is_dir else "Enlace" if is_link else "Archivo"

        lines = [
            f"📄 {target}",
            f"  Tipo:      {file_type}",
            f"  Tamaño:    {format_size(size)}",
            f"  Permisos:  {perms}",
            f"  Modificado:{modified}",
            f"  Creado:    {created}",
        ]

        if is_dir:
            try:
                count = len(os.listdir(target))
                lines.append(f"  Contenido: {count} elementos")
            except PermissionError:
                lines.append(f"  Contenido: Sin permisos")

        if is_link:
            lines.append(f"  Target:    {os.readlink(target)}")

        return "\n".join(lines)
    except Exception as e:
        return f"Error obteniendo info: {e}"


def _search_files(args):
    pattern = args["pattern"]
    path = args.get("path")
    base = safe_path(path)
    if not os.path.isdir(base):
        return f"Error: Directorio no existe: {base}"

    try:
        search_pattern = os.path.join(base, "**", pattern)
        matches = glob.glob(search_pattern, recursive=True)

        if not matches:
            return f"No se encontraron archivos con patrón '{pattern}' en {base}"

        lines = [f"🔍 Resultados para '{pattern}' ({len(matches)} archivos):\n"]
        for match in sorted(matches)[:50]:
            rel = os.path.relpath(match, base)
            try:
                size = format_size(os.path.getsize(match))
            except OSError:
                size = "?"
            lines.append(f"  📄 {rel} ({size})")

        if len(matches) > 50:
            lines.append(f"\n  ... y {len(matches) - 50} más")

        return "\n".join(lines)
    except Exception as e:
        return f"Error en búsqueda: {e}"


def _read_file(args):
    path = args["path"]
    start_line = args.get("start_line", 1)
    end_line = args.get("end_line")
    max_lines = args.get("max_lines", 200)

    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: No existe: {target}"
    if os.path.isdir(target):
        return f"Error: Es un directorio, no un archivo: {target}"

    try:
        file_size = os.path.getsize(target)
        if file_size > MAX_FILE_SIZE:
            return f"Error: Archivo demasiado grande ({format_size(file_size)}). Máximo: {format_size(MAX_FILE_SIZE)}"

        start_line = max(1, start_line or 1)
        with open(target, "r", errors="replace") as f:
            all_lines = f.readlines()

        total_lines = len(all_lines)
        if total_lines == 0:
            return "📄 (Archivo vacío)"

        start_idx = start_line - 1
        if start_idx >= total_lines:
            return f"Error: start_line ({start_line}) supera el total de líneas del archivo ({total_lines})."

        if end_line is not None:
            end_idx = min(total_lines, max(start_line, end_line))
        else:
            end_idx = min(total_lines, start_idx + max_lines)

        selected = all_lines[start_idx:end_idx]
        formatted = []
        for i, line in enumerate(selected, start=start_line):
            formatted.append(f"{i:4d} | {line.rstrip()}")

        header = f"📄 {target} (Líneas {start_line}-{start_line + len(selected) - 1} de {total_lines}):\n"
        result = header + "\n".join(formatted)
        if end_idx < total_lines and end_line is None:
            result += f"\n... ({total_lines - end_idx} líneas restantes no mostradas)"
        return result
    except Exception as e:
        return f"Error leyendo archivo: {e}"


def _write_file(args):
    path = args["path"]
    content = args["content"]
    append = args.get("append", False)
    target = safe_path(path)

    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)

        mode = "a" if append else "w"
        with open(target, mode) as f:
            f.write(content)

        action = "agregado" if append else "escrito"
        size = os.path.getsize(target)
        log_operation("write_file", {"path": path, "append": append}, f"{action} {format_size(size)}")
        return f"✅ Archivo {action}: {target} ({format_size(size)})"
    except Exception as e:
        return f"Error escribiendo archivo: {e}"


def _append_to_file(args):
    path = args["path"]
    content = args["content"]
    target = safe_path(path)
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if not content.startswith("\n") and os.path.exists(target) and os.path.getsize(target) > 0:
            with open(target, "rb") as f:
                f.seek(-1, os.SEEK_END)
                last_char = f.read(1)
                if last_char != b"\n":
                    content = "\n" + content

        with open(target, "a") as f:
            f.write(content)

        size = os.path.getsize(target)
        log_operation("append_to_file", {"path": path}, f"agregado ({format_size(size)})")
        return f"✅ Contenido agregado exitosamente al final de {target} ({format_size(size)})"
    except Exception as e:
        return f"Error anexando a archivo: {e}"


def _replace_file_content(args):
    path = args["path"]
    target_content = args["target_content"]
    replacement_content = args["replacement_content"]
    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: No existe: {target}"
    if os.path.isdir(target):
        return f"Error: Es un directorio: {target}"

    try:
        with open(target, "r", errors="replace") as f:
            data = f.read()

        count = data.count(target_content)
        if count == 0:
            return f"❌ Error: No se encontró 'target_content' en {target}. Verifica los espacios y caracteres exactos."
        if count > 1:
            return f"⚠️ Advertencia: 'target_content' aparece {count} veces en el archivo. Proporciona más contexto para que sea único."

        new_data = data.replace(target_content, replacement_content, 1)
        with open(target, "w") as f:
            f.write(new_data)

        size = os.path.getsize(target)
        log_operation("replace_file_content", {"path": path}, f"reemplazado ({format_size(size)})")
        return f"✅ Contenido reemplazado quirúrgicamente con éxito en {target} ({format_size(size)})"
    except Exception as e:
        return f"Error reemplazando contenido: {e}"


def _compact_context(args):
    content = args["content"]
    try:
        import urllib.request

        system_prompt = (
            "Eres un motor de compactación y síntesis de memoria conversacional. Tu objetivo es resumir "
            "exhaustivamente el texto o historial proporcionado para preservar el contexto completo en una fracción de tokens.\n\n"
            "Estructura el resumen en viñetas densas:\n"
            "• 🎯 **Objetivos y Estado**: Solicitudes del usuario, tareas completadas y pendientes.\n"
            "• 📁 **Archivos y Rutas**: Rutas leídas, creadas o editadas y su propósito.\n"
            "• ⚙️ **Decisiones Técnicas y Comandos**: Arquitectura, variables, parámetros, fórmulas o comandos ejecutados.\n"
            "• 💡 **Preferencias del Usuario**: Notación, idioma o directrices explícitas.\n\n"
            "Sé denso, objetivo y conciso."
        )

        payload = {
            "model": "/home/darkseid/llama.cpp/ai-models/gemma-4-12b-it-Q4_K_M.gguf",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Por favor compacta el siguiente contenido:\n\n{content}"}
            ],
            "temperature": 0.3,
            "max_tokens": 2048
        }

        req = urllib.request.Request(
            "http://127.0.0.1:9090/v1/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            summary = data["choices"][0]["message"]["content"]
            log_operation("compact_context", {"chars_in": len(content), "chars_out": len(summary)}, "compactado con éxito")
            return f"🗜️ **Contexto compactado con éxito:**\n\n{summary}"

    except Exception as e:
        return f"⚠️ Error en compactación de contexto: {e}"


def _run_command(args):
    command = args["command"]
    confirm = args.get("confirm", False)

    if is_blocked_command(command):
        return f"❌ Comando bloqueado por seguridad: {command}"

    if is_destructive_command(command) and not confirm:
        return (
            f"⚠️ Comando destructivo detectado: {command}\n"
            f"Para ejecutar, responde al LLM con confirmación.\n"
            f"El LLM llamará de nuevo con confirm=true."
        )

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT,
            env={**os.environ, "TERM": "dumb"}
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        lines = output.strip().split("\n")
        if len(lines) > MAX_OUTPUT_LINES:
            output = "\n".join(lines[:MAX_OUTPUT_LINES]) + f"\n... ({len(lines)} líneas totales, truncado)"

        log_operation("run_command", {"command": command}, f"exit={result.returncode}")

        if result.returncode != 0:
            return f"⚠️ Comando terminó con código {result.returncode}:\n{output}"
        return output if output else "(sin salida)"

    except subprocess.TimeoutExpired:
        return f"⏰ Comando excedió timeout de {COMMAND_TIMEOUT}s: {command}"
    except Exception as e:
        return f"Error ejecutando comando: {e}"


def _run_python_script(args):
    script = args["script"]
    timeout = args.get("timeout", 30)

    if is_blocked_command(script):
        return "❌ Script bloqueado por seguridad"

    try:
        result = subprocess.run(
            ["python3", "-c", script],
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=HOME
        )

        output = result.stdout
        if result.stderr:
            output += f"\n[STDERR]\n{result.stderr}"

        lines = output.strip().split("\n")
        if len(lines) > MAX_OUTPUT_LINES:
            output = "\n".join(lines[:MAX_OUTPUT_LINES]) + f"\n... (truncado)"

        log_operation("run_python_script", {"script": script[:50]}, f"exit={result.returncode}")

        if result.returncode != 0:
            return f"⚠️ Script terminó con código {result.returncode}:\n{output}"
        return output if output else "(sin salida)"

    except subprocess.TimeoutExpired:
        return f"⏰ Script excedió timeout de {timeout}s"
    except Exception as e:
        return f"Error ejecutando script: {e}"


def _file_compress(args):
    source = safe_path(args["source"])
    fmt = args.get("format", "tar.gz")
    if not os.path.exists(source):
        return f"Error: No existe: {source}"

    try:
        base_name = os.path.basename(source)
        if fmt == "tar.gz":
            dest = f"{source}.tar.gz"
            result = subprocess.run(
                ["tar", "-czf", dest, "-C", os.path.dirname(source), base_name],
                capture_output=True, text=True, timeout=60
            )
        elif fmt == "zip":
            dest = f"{source}.zip"
            result = subprocess.run(
                ["zip", "-r", dest, source],
                capture_output=True, text=True, timeout=60
            )
        else:
            return f"Formato no soportado: {fmt}"

        if result.returncode != 0:
            return f"Error comprimiendo: {result.stderr}"

        size = format_size(os.path.getsize(dest))
        log_operation("file_compress", {"source": source, "format": fmt}, f"{dest} ({size})")
        return f"✅ Comprimido: {dest} ({size})"

    except Exception as e:
        return f"Error comprimiendo: {e}"


def _file_extract(args):
    source = safe_path(args["source"])
    destination = args.get("destination")
    if not os.path.exists(source):
        return f"Error: No existe: {source}"

    try:
        if destination:
            dest = safe_path(destination)
            os.makedirs(dest, exist_ok=True)
        else:
            dest = os.path.dirname(source)

        if source.endswith(".tar.gz") or source.endswith(".tgz"):
            result = subprocess.run(
                ["tar", "-xzf", source, "-C", dest],
                capture_output=True, text=True, timeout=60
            )
        elif source.endswith(".zip"):
            result = subprocess.run(
                ["unzip", "-o", source, "-d", dest],
                capture_output=True, text=True, timeout=60
            )
        elif source.endswith(".tar.bz2"):
            result = subprocess.run(
                ["tar", "-xjf", source, "-C", dest],
                capture_output=True, text=True, timeout=60
            )
        else:
            return f"Formato no soportado: {source}"

        if result.returncode != 0:
            return f"Error extrayendo: {result.stderr}"

        log_operation("file_extract", {"source": source}, f"to {dest}")
        return f"✅ Extraído en: {dest}"

    except Exception as e:
        return f"Error extrayendo: {e}"


def _file_permissions(args):
    path = safe_path(args["path"])
    mode = args["mode"]
    if not os.path.exists(path):
        return f"Error: No existe: {path}"

    try:
        mode_int = int(mode, 8) if isinstance(mode, str) else mode
        os.chmod(path, mode_int)

        log_operation("file_permissions", {"path": path, "mode": mode}, "changed")
        return f"✅ Permisos cambiados: {path} → {mode}"

    except ValueError:
        return f"Error: Modo de permisos no válido: {mode}"
    except Exception as e:
        return f"Error cambiando permisos: {e}"


HANDLERS = {
    "list_directory": _list_directory,
    "file_info": _file_info,
    "search_files": _search_files,
    "read_file": _read_file,
    "write_file": _write_file,
    "append_to_file": _append_to_file,
    "replace_file_content": _replace_file_content,
    "compact_context": _compact_context,
    "run_command": _run_command,
    "run_python_script": _run_python_script,
    "file_compress": _file_compress,
    "file_extract": _file_extract,
    "file_permissions": _file_permissions,
}
