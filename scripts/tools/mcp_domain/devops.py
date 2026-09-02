"""GitHub, Git, code analysis, project structure, and Docker tools."""

import os
import subprocess
import json
import tempfile

from mcp_common.paths import safe_path, format_size
from mcp_common.logging import log_operation

TOOLS = [
    # ── GitHub Tools ────────────────────────────────────────
    {
        "name": "gh_repos_list",
        "description": "Lista repositorios de GitHub del usuario.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Numero de repos. Default: 20."
                },
                "visibility": {
                    "type": "string",
                    "enum": ["all", "public", "private"],
                    "description": "Visibilidad. Default: all."
                }
            },
            "required": []
        }
    },
    {
        "name": "gh_repo_info",
        "description": "Muestra informacion detallada de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Nombre del repositorio (owner/repo o solo repo)."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_repo_create",
        "description": "Crea un nuevo repositorio en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre del repositorio."
                },
                "description": {
                    "type": "string",
                    "description": "Descripcion del repositorio."
                },
                "private": {
                    "type": "boolean",
                    "description": "Si es privado. Default: false."
                },
                "auto_init": {
                    "type": "boolean",
                    "description": "Inicializar con README. Default: true."
                }
            },
            "required": ["name"]
        }
    },
    {
        "name": "gh_issues_list",
        "description": "Lista issues de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Estado. Default: open."
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero de issues. Default: 20."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_issue_create",
        "description": "Crea un issue en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "title": {
                    "type": "string",
                    "description": "Titulo del issue."
                },
                "body": {
                    "type": "string",
                    "description": "Contenido del issue."
                },
                "labels": {
                    "type": "string",
                    "description": "Labels separados por coma."
                }
            },
            "required": ["repo", "title"]
        }
    },
    {
        "name": "gh_pr_list",
        "description": "Lista pull requests de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "state": {
                    "type": "string",
                    "enum": ["open", "closed", "all"],
                    "description": "Estado. Default: open."
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero de PRs. Default: 20."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_pr_create",
        "description": "Crea un pull request en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "title": {
                    "type": "string",
                    "description": "Titulo del PR."
                },
                "body": {
                    "type": "string",
                    "description": "Descripcion del PR."
                },
                "head": {
                    "type": "string",
                    "description": "Branch origen."
                },
                "base": {
                    "type": "string",
                    "description": "Branch destino. Default: main."
                }
            },
            "required": ["repo", "title", "head"]
        }
    },
    {
        "name": "gh_pr_merge",
        "description": "Merge un pull request.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "pr_number": {
                    "type": "integer",
                    "description": "Numero del PR."
                }
            },
            "required": ["repo", "pr_number"]
        }
    },
    {
        "name": "gh_actions_list",
        "description": "Lista GitHub Actions workflows de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_actions_runs",
        "description": "Muestra ejecuciones recientes de GitHub Actions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero de runs. Default: 10."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_release_list",
        "description": "Lista releases de un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "repo": {
                    "type": "string",
                    "description": "Repositorio (owner/repo)."
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero de releases. Default: 10."
                }
            },
            "required": ["repo"]
        }
    },
    {
        "name": "gh_gist_list",
        "description": "Lista tus Gists de GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Numero de gists. Default: 20."
                }
            },
            "required": []
        }
    },
    {
        "name": "gh_gist_create",
        "description": "Crea un Gist en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "filename": {
                    "type": "string",
                    "description": "Nombre del archivo."
                },
                "content": {
                    "type": "string",
                    "description": "Contenido del archivo."
                },
                "description": {
                    "type": "string",
                    "description": "Descripcion del Gist."
                },
                "public": {
                    "type": "boolean",
                    "description": "Si es publico. Default: false."
                }
            },
            "required": ["filename", "content"]
        }
    },
    {
        "name": "gh_search_repos",
        "description": "Busca repositorios en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termino de busqueda."
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero de resultados. Default: 10."
                },
                "language": {
                    "type": "string",
                    "description": "Filtrar por lenguaje."
                },
                "sort": {
                    "type": "string",
                    "enum": ["stars", "forks", "updated"],
                    "description": "Ordenar por. Default: stars."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "gh_search_code",
        "description": "Busca codigo en GitHub.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Termino de busqueda."
                },
                "repo": {
                    "type": "string",
                    "description": "Filtrar por repositorio (owner/repo)."
                },
                "language": {
                    "type": "string",
                    "description": "Filtrar por lenguaje."
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero de resultados. Default: 10."
                }
            },
            "required": ["query"]
        }
    },
    # ── Git Tools ──────────────────────────────────────────
    {
        "name": "git_status",
        "description": "Muestra el estado del repositorio Git actual.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio. Default: directorio actual."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_log",
        "description": "Muestra el historial de commits.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                },
                "limit": {
                    "type": "integer",
                    "description": "Numero de commits. Default: 10."
                },
                "branch": {
                    "type": "string",
                    "description": "Branch a mostrar. Default: actual."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_diff",
        "description": "Muestra diferencias en el repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                },
                "file": {
                    "type": "string",
                    "description": "Archivo especifico a comparar."
                },
                "staged": {
                    "type": "boolean",
                    "description": "Mostrar cambios staged. Default: false."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_branches",
        "description": "Lista branches del repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_commit",
        "description": "Crea un commit con cambios staged.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                },
                "message": {
                    "type": "string",
                    "description": "Mensaje del commit."
                },
                "add_all": {
                    "type": "boolean",
                    "description": "Agregar todos los cambios (git add -A). Default: false."
                }
            },
            "required": ["message"]
        }
    },
    {
        "name": "git_push",
        "description": "Push commits al remote.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                },
                "branch": {
                    "type": "string",
                    "description": "Branch a push. Default: actual."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_pull",
        "description": "Pull cambios del remote.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del repositorio."
                }
            },
            "required": []
        }
    },
    {
        "name": "git_clone",
        "description": "Clona un repositorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL del repositorio a clonar."
                },
                "destination": {
                    "type": "string",
                    "description": "Directorio destino."
                }
            },
            "required": ["url"]
        }
    },
    # ── Code Analysis Tools ───────────────────────────────
    {
        "name": "code_analyze",
        "description": "Analiza un archivo de codigo y muestra estadisticas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del archivo a analizar."
                }
            },
            "required": ["path"]
        }
    },
    {
        "name": "code_count_lines",
        "description": "Cuenta lineas de codigo en un directorio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del directorio."
                },
                "extension": {
                    "type": "string",
                    "description": "Extension a filtrar (ej: 'py', 'js')."
                }
            },
            "required": []
        }
    },
    {
        "name": "code_search_pattern",
        "description": "Busca un patron en archivos de codigo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Patron regex a buscar."
                },
                "path": {
                    "type": "string",
                    "description": "Directorio a buscar."
                },
                "extension": {
                    "type": "string",
                    "description": "Extension de archivo."
                }
            },
            "required": ["pattern"]
        }
    },
    {
        "name": "project_dependencies",
        "description": "Muestra dependencias de un proyecto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del proyecto."
                }
            },
            "required": []
        }
    },
    {
        "name": "project_structure",
        "description": "Muestra la estructura de un proyecto.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Ruta del proyecto."
                },
                "depth": {
                    "type": "integer",
                    "description": "Profundidad maxima. Default: 3."
                }
            },
            "required": []
        }
    },
    # ── Docker Tools ───────────────────────────────────────
    {
        "name": "docker_ps",
        "description": "Muestra contenedores Docker activos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "all": {
                    "type": "boolean",
                    "description": "Mostrar todos (incluyendo detenidos). Default: false."
                }
            },
            "required": []
        }
    },
    {
        "name": "docker_logs",
        "description": "Muestra logs de un contenedor Docker.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "container": {
                    "type": "string",
                    "description": "Nombre o ID del contenedor."
                },
                "lines": {
                    "type": "integer",
                    "description": "Numero de lineas. Default: 50."
                }
            },
            "required": ["container"]
        }
    },
    {
        "name": "docker_images",
        "description": "Muestra imagenes Docker disponibles.",
        "inputSchema": {
            "type": "object",
            "properties": {}
        }
    },
]

# ── Handlers ───────────────────────────────────────────────

GH = "gh"


def _gh(args: list, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            [GH] + args,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except FileNotFoundError:
        return "Error: GitHub CLI (gh) no instalado"
    except subprocess.TimeoutExpired:
        return "Timeout en operacion de GitHub"
    except Exception as e:
        return f"Error: {e}"


def _git(args: list, path: str = None, timeout: int = 30) -> str:
    try:
        cmd = ["git"] + args
        result = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=timeout,
            cwd=path or os.getcwd()
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except FileNotFoundError:
        return "Error: Git no instalado"
    except Exception as e:
        return f"Error: {e}"


def _docker(args: list, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            ["docker"] + args,
            capture_output=True, text=True, timeout=timeout
        )
        if result.returncode != 0:
            return f"Error: {result.stderr.strip()}"
        return result.stdout.strip()
    except FileNotFoundError:
        return "Error: Docker no instalado"
    except Exception as e:
        return f"Error: {e}"


def _gh_repos_list(args):
    limit = args.get("limit", 20)
    visibility = args.get("visibility", "all")
    args_list = ["repo", "list", "--limit", str(limit), "--json", "name,description,isPrivate,updatedAt,stargazerCount"]
    if visibility and visibility != "all":
        args_list.extend(["--visibility", visibility])
    output = _gh(args_list)
    if output.startswith("Error"):
        return output

    try:
        repos = json.loads(output)
        if not repos:
            return "No hay repositorios"

        lines = [f"Repositorios ({len(repos)}):\n"]
        for r in repos:
            vis = "Privado" if r.get("isPrivate") else "Publico"
            stars = f"Stars:{r.get('stargazerCount', 0)}" if r.get('stargazerCount', 0) > 0 else ""
            lines.append(f"  {vis} {r['name']} {stars}")
            if r.get('description'):
                lines.append(f"     {r['description'][:80]}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def _gh_repo_info(args):
    repo = args.get("repo", "")
    output = _gh(["repo", "view", repo, "--json", "name,description,isPrivate,homepageUrl,primaryLanguage,stargazerCount,forkCount,watchers,createdAt,updatedAt,pushedAt,defaultBranchRef"])
    if output.startswith("Error"):
        return output

    try:
        r = json.loads(output)
        lang = r.get('primaryLanguage', {}).get('name', 'N/A') if r.get('primaryLanguage') else 'N/A'
        vis = "Privado" if r.get('isPrivate') else "Publico"

        info = [
            f"{r['name']}",
            f"  Descripcion: {r.get('description', 'N/A')}",
            f"  Visibilidad: {vis}",
            f"  Lenguaje: {lang}",
            f"  Stars: {r.get('stargazerCount', 0)}",
            f"  Forks: {r.get('forkCount', 0)}",
            f"  Watchers: {r.get('watchers', {}).get('totalCount', 0)}",
            f"  Creado: {r.get('createdAt', 'N/A')}",
            f"  Ultimo push: {r.get('pushedAt', 'N/A')}",
        ]
        return "\n".join(info)
    except json.JSONDecodeError:
        return output


def _gh_repo_create(args):
    name = args.get("name", "")
    description = args.get("description")
    private = args.get("private", False)
    auto_init = args.get("auto_init", True)
    args_list = ["repo", "create", name]
    if description:
        args_list.extend(["-d", description])
    if private:
        args_list.append("--private")
    else:
        args_list.append("--public")
    if auto_init:
        args_list.append("--clone")

    output = _gh(args_list)
    return f"Repositorio creado: {output}" if not output.startswith("Error") else output


def _gh_issues_list(args):
    repo = args.get("repo", "")
    state = args.get("state", "open")
    limit = args.get("limit", 20)
    output = _gh(["issue", "list", "-R", repo, "--state", state, "--limit", str(limit), "--json", "number,title,state,labels,createdAt"])
    if output.startswith("Error"):
        return output

    try:
        issues = json.loads(output)
        if not issues:
            return f"No hay issues {state} en {repo}"

        lines = [f"Issues {state} en {repo} ({len(issues)}):\n"]
        for i in issues:
            labels = ", ".join(l['name'] for l in i.get('labels', []))
            label_str = f" [{labels}]" if labels else ""
            lines.append(f"  #{i['number']} {i['title']}{label_str}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def _gh_issue_create(args):
    repo = args.get("repo", "")
    title = args.get("title", "")
    body = args.get("body")
    labels = args.get("labels")
    args_list = ["issue", "create", "-R", repo, "-t", title]
    if body:
        args_list.extend(["-b", body])
    if labels:
        args_list.extend(["-l", labels])

    output = _gh(args_list)
    return f"Issue creado: {output}" if not output.startswith("Error") else output


def _gh_pr_list(args):
    repo = args.get("repo", "")
    state = args.get("state", "open")
    limit = args.get("limit", 20)
    output = _gh(["pr", "list", "-R", repo, "--state", state, "--limit", str(limit), "--json", "number,title,state,author,createdAt,headRefName,baseRefName"])
    if output.startswith("Error"):
        return output

    try:
        prs = json.loads(output)
        if not prs:
            return f"No hay PRs {state} en {repo}"

        lines = [f"Pull Requests {state} en {repo} ({len(prs)}):\n"]
        for pr in prs:
            author = pr.get('author', {}).get('login', 'unknown')
            lines.append(f"  #{pr['number']} {pr['title']} (by @{author})")
            lines.append(f"     {pr.get('headRefName', '?')} -> {pr.get('baseRefName', '?')}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def _gh_pr_create(args):
    repo = args.get("repo", "")
    title = args.get("title", "")
    body = args.get("body")
    head = args.get("head")
    base = args.get("base", "main")
    args_list = ["pr", "create", "-R", repo, "-t", title]
    if body:
        args_list.extend(["-b", body])
    if head:
        args_list.extend(["-H", head])
    args_list.extend(["-B", base])

    output = _gh(args_list)
    return f"PR creado: {output}" if not output.startswith("Error") else output


def _gh_pr_merge(args):
    repo = args.get("repo", "")
    pr_number = args.get("pr_number")
    output = _gh(["pr", "merge", str(pr_number), "-R", repo, "--merge"])
    return f"PR #{pr_number} mergeado" if not output.startswith("Error") else output


def _gh_actions_list(args):
    repo = args.get("repo", "")
    output = _gh(["workflow", "list", "-R", repo, "--json", "name,state,createdAt"])
    if output.startswith("Error"):
        return output

    try:
        workflows = json.loads(output)
        if not workflows:
            return f"No hay workflows en {repo}"

        lines = [f"Workflows en {repo} ({len(workflows)}):\n"]
        for w in workflows:
            state_icon = {"active": "OK", "disabled": "OFF"}.get(w.get('state', ''), "?")
            lines.append(f"  {state_icon} {w['name']} ({w.get('state', 'unknown')})")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def _gh_actions_runs(args):
    repo = args.get("repo", "")
    limit = args.get("limit", 10)
    output = _gh(["run", "list", "-R", repo, "--limit", str(limit), "--json", "name,status,conclusion,createdAt,event"])
    if output.startswith("Error"):
        return output

    try:
        runs = json.loads(output)
        if not runs:
            return f"No hay runs en {repo}"

        lines = [f"Runs recientes en {repo} ({len(runs)}):\n"]
        for r in runs:
            status_icon = {"success": "OK", "failure": "FAIL", "in_progress": "RUN"}.get(r.get('conclusion', r.get('status', '')), "?")
            lines.append(f"  {status_icon} {r['name']} - {r.get('conclusion', r.get('status', 'unknown'))}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def _gh_release_list(args):
    repo = args.get("repo", "")
    limit = args.get("limit", 10)
    output = _gh(["release", "list", "-R", repo, "--limit", str(limit)])
    if output.startswith("Error"):
        return output

    if not output:
        return f"No hay releases en {repo}"

    return f"Releases en {repo}:\n{output}"


def _gh_gist_list(args):
    limit = args.get("limit", 20)
    output = _gh(["gist", "list", "--limit", str(limit), "--json", "name,description,public,updatedAt"])
    if output.startswith("Error"):
        return output

    try:
        gists = json.loads(output)
        if not gists:
            return "No hay gists"

        lines = [f"Tus Gists ({len(gists)}):\n"]
        for g in gists:
            vis = "Publico" if g.get('public') else "Privado"
            desc = f" - {g['description']}" if g.get('description') else ""
            lines.append(f"  {vis} {g['name']}{desc}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def _gh_gist_create(args):
    filename = args.get("filename", "")
    content = args.get("content", "")
    description = args.get("description")
    public = args.get("public", False)
    args_list = ["gist", "create"]
    if description:
        args_list.extend(["-d", description])
    if public:
        args_list.append("--public")
    else:
        args_list.append("--secret")

    with tempfile.NamedTemporaryFile(mode='w', suffix=f"_{filename}", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    try:
        args_list.append(tmp_path)
        output = _gh(args_list)
        return f"Gist creado: {output}" if not output.startswith("Error") else output
    finally:
        os.unlink(tmp_path)


def _gh_search_repos(args):
    query = args.get("query", "")
    limit = args.get("limit", 10)
    language = args.get("language")
    sort = args.get("sort", "stars")
    search_query = query
    if language:
        search_query += f" language:{language}"

    output = _gh(["search", "repos", search_query, "--limit", str(limit), "--sort", sort, "--json", "name,description,stargazersCount,language"])
    if output.startswith("Error"):
        return output

    try:
        repos = json.loads(output)
        if not repos:
            return f"No se encontraron repositorios para: {query}"

        lines = [f"Repositorios para '{query}' ({len(repos)}):\n"]
        for r in repos:
            stars = f"Stars:{r.get('stargazersCount', 0)}" if r.get('stargazersCount', 0) > 0 else ""
            lang = f"({r.get('language', 'N/A')})" if r.get('language') else ""
            lines.append(f"  {r['name']} {stars} {lang}")
            if r.get('description'):
                lines.append(f"     {r['description'][:80]}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def _gh_search_code(args):
    query = args.get("query", "")
    repo = args.get("repo")
    language = args.get("language")
    limit = args.get("limit", 10)
    search_query = query
    if repo:
        search_query += f" repo:{repo}"
    if language:
        search_query += f" language:{language}"

    output = _gh(["search", "code", search_query, "--limit", str(limit), "--json", "name,path,repository"])
    if output.startswith("Error"):
        return output

    try:
        results = json.loads(output)
        if not results:
            return f"No se encontro codigo para: {query}"

        lines = [f"Codigo para '{query}' ({len(results)} resultados):\n"]
        for r in results:
            repo_name = r.get('repository', {}).get('name', 'unknown')
            lines.append(f"  {repo_name}/{r['path']}")

        return "\n".join(lines)
    except json.JSONDecodeError:
        return output


def _git_status(args):
    path = args.get("path")
    output = _git(["status", "--short"], path)
    if output.startswith("Error"):
        return output

    if not output:
        return "Working tree limpio"

    lines = [f"Estado Git:\n"]
    for line in output.split("\n"):
        if line.strip():
            lines.append(f"  {line}")

    return "\n".join(lines)


def _git_log(args):
    path = args.get("path")
    limit = args.get("limit", 10)
    branch = args.get("branch")
    args_list = ["log", f"--oneline", f"-{limit}"]
    if branch:
        args_list.append(branch)

    output = _git(args_list, path)
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay commits"

    return f"Historial ({limit} commits):\n{output}"


def _git_diff(args):
    path = args.get("path")
    file = args.get("file")
    staged = args.get("staged", False)
    args_list = ["diff"]
    if staged:
        args_list.append("--staged")
    if file:
        args_list.append(file)

    output = _git(args_list, path)
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay cambios"

    lines = output.split("\n")[:50]
    return f"Diferencias:\n" + "\n".join(lines) + ("\n... (truncado)" if len(output.split("\n")) > 50 else "")


def _git_branches(args):
    path = args.get("path")
    output = _git(["branch", "-a"], path)
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay branches"

    lines = ["Branches:\n"]
    for line in output.split("\n"):
        if line.strip():
            lines.append(f"  {line}")

    return "\n".join(lines)


def _git_commit(args):
    path = args.get("path")
    message = args.get("message")
    add_all = args.get("add_all", False)
    if not message:
        return "Error: Se requiere mensaje de commit"

    if add_all:
        _git(["add", "-A"], path)

    output = _git(["commit", "-m", message], path)
    if output.startswith("Error"):
        return output

    log_operation("git_commit", {"message": message}, "committed")
    return f"Commit creado: {message}"


def _git_push(args):
    path = args.get("path")
    branch = args.get("branch")
    args_list = ["push"]
    if branch:
        args_list.extend(["origin", branch])
    else:
        args_list.append("origin")

    output = _git(args_list, path)
    if output.startswith("Error"):
        return output

    log_operation("git_push", {}, "pushed")
    return f"Push completado\n{output}" if output else "Push completado"


def _git_pull(args):
    path = args.get("path")
    output = _git(["pull", "origin"], path)
    if output.startswith("Error"):
        return output

    log_operation("git_pull", {}, "pulled")
    return f"Pull completado\n{output}" if output else "Pull completado"


def _git_clone(args):
    url = args.get("url", "")
    destination = args.get("destination")
    args_list = ["clone", url]
    if destination:
        args_list.append(destination)

    output = _git(args_list)
    if output.startswith("Error"):
        return output

    log_operation("git_clone", {"url": url}, "cloned")
    return f"Repositorio clonado: {url}"


def _code_analyze(args):
    path = args.get("path", "")
    target = safe_path(path)
    if not os.path.exists(target):
        return f"Error: No existe: {target}"

    try:
        with open(target, "r", errors="replace") as f:
            content = f.read()

        lines = content.split("\n")
        total_lines = len(lines)
        blank_lines = sum(1 for l in lines if not l.strip())
        comment_lines = sum(1 for l in lines if l.strip().startswith(("#", "//", "/*", "*", "<!--")))
        code_lines = total_lines - blank_lines - comment_lines

        ext = os.path.splitext(target)[1]
        size = format_size(os.path.getsize(target))

        info = [
            f"Analisis de {os.path.basename(target)}",
            f"  Tamano: {size}",
            f"  Extension: {ext}",
            f"  Lineas totales: {total_lines}",
            f"  Codigo: {code_lines}",
            f"  Comentarios: {comment_lines}",
            f"  En blanco: {blank_lines}",
        ]

        return "\n".join(info)

    except Exception as e:
        return f"Error analizando archivo: {e}"


def _code_count_lines(args):
    path = args.get("path")
    extension = args.get("extension")
    target = safe_path(path) if path else os.getcwd()

    if not os.path.isdir(target):
        return f"Error: No es directorio: {target}"

    try:
        total = 0
        by_ext = {}

        for root, dirs, files in os.walk(target):
            dirs[:] = [d for d in dirs if not d.startswith(".") and d not in ["node_modules", "__pycache__", "venv", ".venv", "vendor"]]

            for f in files:
                if extension and not f.endswith(f".{extension}"):
                    continue

                filepath = os.path.join(root, f)
                try:
                    with open(filepath, "r", errors="replace") as fh:
                        lines = sum(1 for _ in fh)
                        total += lines

                        ext = os.path.splitext(f)[1] or "no_ext"
                        by_ext[ext] = by_ext.get(ext, 0) + lines
                except:
                    pass

        lines = [f"Lineas de codigo en {target}:\n"]
        lines.append(f"  Total: {total} lineas\n")
        lines.append("  Por extension:")

        for ext, count in sorted(by_ext.items(), key=lambda x: -x[1])[:15]:
            lines.append(f"    {ext}: {count}")

        return "\n".join(lines)

    except Exception as e:
        return f"Error contando lineas: {e}"


def _code_search_pattern(args):
    pattern = args.get("pattern", "")
    path = args.get("path")
    extension = args.get("extension")
    target = safe_path(path) if path else os.getcwd()

    try:
        cmd = ["grep", "-rn", "--include", f"*.{extension}" if extension else "*", pattern, target]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            return f"No se encontro el patron: {pattern}"

        matches = result.stdout.strip().split("\n")
        lines = [f"Patron '{pattern}' ({len(matches)} coincidencias):\n"]

        for match in matches[:20]:
            lines.append(f"  {match}")

        if len(matches) > 20:
            lines.append(f"\n  ... y {len(matches) - 20} mas")

        return "\n".join(lines)

    except Exception as e:
        return f"Error buscando patron: {e}"


def _project_dependencies(args):
    path = args.get("path")
    target = safe_path(path) if path else os.getcwd()

    deps = []

    req_file = os.path.join(target, "requirements.txt")
    if os.path.exists(req_file):
        with open(req_file) as f:
            deps.append(("Python (requirements.txt)", [l.strip() for l in f if l.strip() and not l.startswith("#")]))

    pkg_file = os.path.join(target, "package.json")
    if os.path.exists(pkg_file):
        try:
            with open(pkg_file) as f:
                pkg = json.load(f)
                all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                deps.append(("Node.js (package.json)", list(all_deps.keys())))
        except:
            pass

    cargo_file = os.path.join(target, "Cargo.toml")
    if os.path.exists(cargo_file):
        with open(cargo_file) as f:
            in_deps = False
            rust_deps = []
            for line in f:
                if "[dependencies]" in line:
                    in_deps = True
                elif line.startswith("["):
                    in_deps = False
                elif in_deps and "=" in line:
                    rust_deps.append(line.split("=")[0].strip())
            deps.append(("Rust (Cargo.toml)", rust_deps))

    if not deps:
        return f"No se encontraron dependencias en {target}"

    lines = [f"Dependencias en {target}:\n"]
    for name, dep_list in deps:
        lines.append(f"  {name}:")
        for d in dep_list[:20]:
            lines.append(f"    - {d}")
        if len(dep_list) > 20:
            lines.append(f"    ... y {len(dep_list) - 20} mas")
        lines.append("")

    return "\n".join(lines)


def _project_structure(args):
    path = args.get("path")
    depth = args.get("depth", 3)
    target = safe_path(path) if path else os.getcwd()

    if not os.path.isdir(target):
        return f"Error: No es directorio: {target}"

    try:
        lines = [f"Estructura de {os.path.basename(target)}:\n"]

        def tree(dir_path, prefix="", current_depth=0):
            if current_depth >= depth:
                return

            try:
                entries = sorted(os.listdir(dir_path))
            except PermissionError:
                return

            dirs = [e for e in entries if os.path.isdir(os.path.join(dir_path, e)) and not e.startswith(".") and e not in ["node_modules", "__pycache__", "venv", ".venv"]]
            files = [e for e in entries if os.path.isfile(os.path.join(dir_path, e)) and not e.startswith(".")]

            for d in dirs[:10]:
                lines.append(f"{prefix}+-- {d}/")
                tree(os.path.join(dir_path, d), prefix + "|   ", current_depth + 1)

            for f in files[:5]:
                lines.append(f"{prefix}+-- {f}")

            if len(dirs) > 10:
                lines.append(f"{prefix}+-- ... ({len(dirs) - 10} mas)")

        tree(target)
        return "\n".join(lines)

    except Exception as e:
        return f"Error mostrando estructura: {e}"


def _docker_ps(args):
    all_containers = args.get("all", False)
    args_list = ["ps", "--format", "table {{.ID}}\t{{.Names}}\t{{.Status}}\t{{.Ports}}"]
    if all_containers:
        args_list.append("-a")

    output = _docker(args_list)
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay contenedores"

    return f"Contenedores:\n{output}"


def _docker_logs(args):
    container = args.get("container", "")
    lines_count = args.get("lines", 50)
    try:
        result = subprocess.run(
            ["docker", "logs", "--tail", str(lines_count), container],
            capture_output=True, text=True, timeout=30
        )
        output = (result.stdout + result.stderr).strip()
        if result.returncode != 0 and not output:
            return f"Error: {result.stderr.strip() or 'Container not found'}"
        if not output:
            return f"No hay logs para {container}"
        return f"Logs de {container} (ultimas {lines_count} lineas):\n{output}"
    except FileNotFoundError:
        return "Error: Docker no instalado"
    except Exception as e:
        return f"Error: {e}"


def _docker_images(args):
    output = _docker(["images", "--format", "table {{.Repository}}\t{{.Tag}}\t{{.Size}}"])
    if output.startswith("Error"):
        return output

    if not output:
        return "No hay imagenes"

    return f"Imagenes:\n{output}"


HANDLERS = {
    "gh_repos_list": _gh_repos_list,
    "gh_repo_info": _gh_repo_info,
    "gh_repo_create": _gh_repo_create,
    "gh_issues_list": _gh_issues_list,
    "gh_issue_create": _gh_issue_create,
    "gh_pr_list": _gh_pr_list,
    "gh_pr_create": _gh_pr_create,
    "gh_pr_merge": _gh_pr_merge,
    "gh_actions_list": _gh_actions_list,
    "gh_actions_runs": _gh_actions_runs,
    "gh_release_list": _gh_release_list,
    "gh_gist_list": _gh_gist_list,
    "gh_gist_create": _gh_gist_create,
    "gh_search_repos": _gh_search_repos,
    "gh_search_code": _gh_search_code,
    "git_status": _git_status,
    "git_log": _git_log,
    "git_diff": _git_diff,
    "git_branches": _git_branches,
    "git_commit": _git_commit,
    "git_push": _git_push,
    "git_pull": _git_pull,
    "git_clone": _git_clone,
    "code_analyze": _code_analyze,
    "code_count_lines": _code_count_lines,
    "code_search_pattern": _code_search_pattern,
    "project_dependencies": _project_dependencies,
    "project_structure": _project_structure,
    "docker_ps": _docker_ps,
    "docker_logs": _docker_logs,
    "docker_images": _docker_images,
}
