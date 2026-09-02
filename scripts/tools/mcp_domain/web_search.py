"""Web search and article fetching tools"""

import os

import re

from mcp_common.logging import log_operation
from mcp_common.security import is_safe_url
from mcp_common.audit import record_system_error

TOOLS = [
    {
        "name": "web_search",
        "description": "Busca en internet usando DuckDuckGo. Retorna resultados relevantes con títulos, URLs y snippets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Número máximo de resultados. Default: 5."
                },
                "region": {
                    "type": "string",
                    "description": "Región para búsqueda (ej: 'mx-es', 'us-en'). Default: 'wt-wt' (global)."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_google",
        "description": "Búsqueda en Google con soporte para AI Mode. Mejor que DuckDuckGo para noticias y eventos recientes.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados.",
                    "default": 10
                },
                "language": {
                    "type": "string",
                    "description": "Idioma (es, en, etc.).",
                    "default": "es"
                },
                "region": {
                    "type": "string",
                    "description": "Región (mx, us, etc.).",
                    "default": "mx"
                },
                "time_filter": {
                    "type": "string",
                    "enum": ["hour", "day", "week", "month", "year"],
                    "description": "Filtrar por tiempo."
                },
                "site": {
                    "type": "string",
                    "description": "Sitio específico (ej: espn.com, marca.com)."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_news",
        "description": "Busca noticias recientes en DuckDuckGo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "region": {
                    "type": "string",
                    "description": "Región (ej: mx-mx, us-en).",
                    "default": "wt-wt"
                },
                "time": {
                    "type": "string",
                    "enum": ["d", "w", "m", "y"],
                    "description": "Período: día, semana, mes, año.",
                    "default": "w"
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados.",
                    "default": 10
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_docs",
        "description": "Busca documentación técnica (Stack Overflow, GitHub, MDN, etc.).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "language": {
                    "type": "string",
                    "description": "Lenguaje de programación (ej: python, javascript)."
                },
                "max_results": {
                    "type": "integer",
                    "description": "Máximo de resultados.",
                    "default": 5
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "search_sports",
        "description": "Búsqueda de resultados deportivos en vivo. Fútbol,篮球, tenis, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Búsqueda (ej: 'Real Madrid vs Barcelona', 'Liga MX resultados')."
                },
                "sport": {
                    "type": "string",
                    "enum": ["football", "basketball", "tennis", "f1", "mma", "other"],
                    "description": "Tipo de deporte.",
                    "default": "football"
                },
                "live": {
                    "type": "boolean",
                    "description": "Buscar solo partidos en vivo.",
                    "default": False
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "fetch_article",
        "description": "Obtiene contenido completo de un artículo web usando BeautifulSoup. Limpia HTML y retorna texto limpio.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL del artículo."
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Máximo de caracteres.",
                    "default": 5000
                },
                "extract_links": {
                    "type": "boolean",
                    "description": "Incluir enlaces encontrados.",
                    "default": False
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "search_with_content",
        "description": "Busca en Google y obtiene el contenido completo del primer resultado. Ideal para respuestas rápidas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Término de búsqueda."
                },
                "max_chars": {
                    "type": "integer",
                    "description": "Máximo de caracteres del contenido.",
                    "default": 3000
                },
                "site": {
                    "type": "string",
                    "description": "Sitio específico."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "browse_web",
        "description": "Obtiene contenido de una URL. Retorna texto, HTML, o JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL a obtener."
                },
                "format": {
                    "type": "string",
                    "enum": ["text", "html", "json"],
                    "description": "Formato de salida.",
                    "default": "text"
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos.",
                    "default": 30
                }
            },
            "required": ["url"]
        }
    },
    {
        "name": "http_request",
        "description": "Realiza petición HTTP (GET, POST, PUT, DELETE, PATCH).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "URL del endpoint."
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"],
                    "description": "Método HTTP.",
                    "default": "GET"
                },
                "headers": {
                    "type": "object",
                    "description": "Headers HTTP."
                },
                "body": {
                    "type": "string",
                    "description": "Body de la petición (JSON o texto)."
                },
                "timeout": {
                    "type": "integer",
                    "description": "Timeout en segundos.",
                    "default": 30
                }
            },
            "required": ["url"]
        }
    },
]

def _google_search(query: str, max_results: int = 10, language: str = "es", 
                   region: str = "mx", time_filter: str = None, site: str = None) -> list:
    """Perform Google search via scraping."""
    try:
        import requests
        from bs4 import BeautifulSoup

        # Build search URL
        search_query = query
        if site:
            search_query = f"site:{site} {query}"

        params = {
            "q": search_query,
            "hl": language,
            "gl": region,
            "num": max_results
        }

        if time_filter:
            time_map = {"hour": "h1", "day": "d1", "week": "w1", "month": "m1", "year": "y1"}
            params["tbs"] = f"qdr:{time_map.get(time_filter, 'w1')}"

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept-Language": f"{language},{language};q=0.9"
        }

        response = requests.get("https://www.google.com/search", params=params, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, "lxml")

        results = []

        # Parse search results
        for g in soup.select("div.g"):
            title_el = g.select_one("h3")
            link_el = g.select_one("a")
            snippet_el = g.select_one("div[data-sncf], span.aCOpRe, div.VwiC3b")

            if title_el and link_el:
                title = title_el.get_text(strip=True)
                url = link_el.get("href", "")
                snippet = snippet_el.get_text(strip=True) if snippet_el else ""

                if url.startswith("/url?q="):
                    url = url.split("/url?q=")[1].split("&")[0]

                if url.startswith("http"):
                    results.append({
                        "title": title,
                        "url": url,
                        "snippet": snippet[:300]
                    })

            if len(results) >= max_results:
                break

        # Also try to extract AI Mode / featured snippet
        ai_snippet = soup.select_one("div[data-attrid='wa:/description'], div.kb0PBd, div.LGOjhe")
        if ai_snippet:
            ai_text = ai_snippet.get_text(strip=True)
            if ai_text and len(ai_text) > 20:
                results.insert(0, {
                    "title": "🤖 Respuesta AI de Google",
                    "url": "",
                    "snippet": ai_text[:500],
                    "is_ai_mode": True
                })

        return results

    except Exception as e:
        return []



# ── Handlers ───────────────────────────────────────────────
def _web_search_handler(query: str, max_results: int = 5, region: str = "wt-wt") -> str:
    """Web search with Google primary, DuckDuckGo fallback."""
    try:
        # Try Google first (better results)
        results = _google_search(query, max_results, "es", "mx")

        if not results:
            # Fallback to DuckDuckGo
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.text(query, region=region, max_results=max_results))
            except ImportError:
                pass

        if not results:
            return f"No se encontraron resultados para: {query}"

        lines = [f"🔍 Resultados para '{query}' ({len(results)} resultados):\n"]

        for i, r in enumerate(results, 1):
            title = r.get("title", "Sin título")
            url = r.get("href", r.get("link", ""))
            snippet = r.get("body", r.get("snippet", ""))[:200]

            lines.append(f"  {i}. {title}")
            lines.append(f"     URL: {url}")
            if snippet:
                lines.append(f"     {snippet}")
            lines.append("")

        log_operation("web_search", {"query": query}, f"{len(results)} results")
        return "\n".join(lines)

    except Exception as e:
        return f"Error en búsqueda: {e}"



def _search_google_handler(query: str, max_results: int = 10, language: str = "es",
                       region: str = "mx", time_filter: str = None, site: str = None) -> str:
    """Search Google with AI Mode support."""
    try:
        results = _google_search(query, max_results, language, region, time_filter, site)

        if not results:
            # Fallback to DuckDuckGo
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    ddg_results = list(ddgs.text(query, max_results=max_results))

                if ddg_results:
                    output = f"🔍 Resultados para '{query}' (DuckDuckGo fallback):\n\n"
                    for i, r in enumerate(ddg_results, 1):
                        output += f"{i}. **{r.get('title', 'N/A')}**\n"
                        output += f"   URL: {r.get('href', 'N/A')}\n"
                        output += f"   {r.get('body', 'N/A')[:200]}\n\n"
                    return output
            except Exception:
                pass

            return f"No se encontraron resultados para: {query}"

        output = f"🔍 Resultados Google para '{query}' ({len(results)} resultados):\n\n"

        for i, r in enumerate(results, 1):
            if r.get("is_ai_mode"):
                output += f"🤖 **AI Mode:**\n{r['snippet']}\n\n"
            else:
                output += f"{i}. **{r['title']}**\n"
                output += f"   URL: {r['url']}\n"
                if r['snippet']:
                    output += f"   {r['snippet']}\n"
                output += "\n"

        log_operation("search_google", {"query": query}, f"{len(results)} results")
        return output

    except Exception as e:
        return f"Error en búsqueda Google: {e}"



def _search_news_handler(query: str, region: str = "wt-wt", time: str = "w", max_results: int = 10) -> str:
    """Search news via DuckDuckGo."""
    try:
        from duckduckgo_search import DDGS
        
        with DDGS() as ddgs:
            results = list(ddgs.news(query, region=region, timelimit=time, max_results=max_results))
        
        if not results:
            return "No se encontraron noticias."
        
        output = f"Noticias para '{query}':\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. **{r.get('title', 'N/A')}**\n"
            output += f"   Fuente: {r.get('source', 'N/A')}\n"
            output += f"   Fecha: {r.get('date', 'N/A')}\n"
            output += f"   URL: {r.get('url', 'N/A')}\n\n"
        
        return output
    
    except Exception as e:
        return f"Error buscando noticias: {e}"



def _search_docs_handler(query: str, language: str = None, max_results: int = 5) -> str:
    """Search technical documentation."""
    try:
        from duckduckgo_search import DDGS
        
        search_query = query
        if language:
            search_query = f"{language} {query} documentation"
        
        with DDGS() as ddgs:
            results = list(ddgs.text(search_query, max_results=max_results))
        
        if not results:
            return "No se encontró documentación."
        
        output = f"Documentación para '{query}':\n\n"
        for i, r in enumerate(results, 1):
            output += f"{i}. **{r.get('title', 'N/A')}**\n"
            output += f"   {r.get('body', 'N/A')[:200]}\n"
            output += f"   URL: {r.get('href', 'N/A')}\n\n"
        
        return output
    
    except Exception as e:
        return f"Error buscando docs: {e}"



def _search_sports_handler(query: str, sport: str = "football", live: bool = False) -> str:
    """Search for sports results."""
    try:
        # Build sport-specific query
        sport_sites = {
            "football": ["espndeportes.espn.com", "marca.com", "as.com", ".goal.com", "flashscore.com"],
            "basketball": ["espn.com/nba", "marca.com/baloncesto"],
            "tennis": ["espn.com/tenis", "marca.com/tenis"],
            "f1": ["espn.com/f1", "marca.com/motor"],
            "mma": ["espn.com/mma", "sherdog.com"]
        }

        sites = sport_sites.get(sport, sport_sites["football"])

        # Try Google first
        search_query = query
        if live:
            search_query += " en vivo HOY"

        results = _google_search(search_query, max_results=5, language="es", region="mx")

        if not results:
            # Try specific sports sites
            for site in sites[:2]:
                results = _google_search(f"{query} site:{site}", max_results=3)
                if results:
                    break

        if not results:
            # Fallback to DuckDuckGo news
            try:
                from duckduckgo_search import DDGS
                with DDGS() as ddgs:
                    results = list(ddgs.news(f"{query} {sport} resultados", max_results=5))

                if results:
                    output = f"⚽ Resultados deportivos para '{query}':\n\n"
                    for i, r in enumerate(results, 1):
                        output += f"{i}. **{r.get('title', 'N/A')}**\n"
                        output += f"   Fuente: {r.get('source', 'N/A')}\n"
                        output += f"   {r.get('url', 'N/A')}\n\n"
                    return output
            except Exception:
                pass

            return f"No se encontraron resultados deportivos para: {query}"

        output = f"⚽ Resultados deportivos para '{query}':\n\n"

        for i, r in enumerate(results[:5], 1):
            output += f"{i}. **{r['title']}**\n"
            output += f"   {r['url']}\n"
            if r['snippet']:
                output += f"   {r['snippet'][:200]}\n"
            output += "\n"

        log_operation("search_sports", {"query": query, "sport": sport}, f"{len(results)} results")
        return output

    except Exception as e:
        return f"Error buscando deportes: {e}"



def _fetch_article_handler(url: str, max_chars: int = 5000, extract_links: bool = False) -> str:
    """Fetch and extract article content using BeautifulSoup."""
    try:
        if not is_safe_url(url):
            return f"Error: URL blocked by security policy (SSRF): {url}"
        import requests
        from bs4 import BeautifulSoup

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Remove unwanted elements
        for tag in soup.select("script, style, nav, footer, header, aside, .ad, .advertisement, .sidebar"):
            tag.decompose()

        # Try to find main content
        article = None
        selectors = [
            "article", "main", "[role='main']",
            ".article-content", ".post-content", ".entry-content",
            ".story-body", ".article-body", ".content-body"
        ]

        for selector in selectors:
            article = soup.select_one(selector)
            if article:
                break

        if not article:
            article = soup.body or soup

        # Extract text
        text = article.get_text(separator="\n", strip=True)

        # Clean up whitespace
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = re.sub(r' {2,}', ' ', text)

        # Extract title
        title = ""
        title_tag = soup.select_one("h1") or soup.select_one("title")
        if title_tag:
            title = title_tag.get_text(strip=True)

        # Build output
        output = f"📄 **{title}**\n"
        output += f"🌐 {url}\n\n"
        output += text[:max_chars]

        if len(text) > max_chars:
            output += f"\n\n... [{len(text) - max_chars} caracteres más]"

        # Extract links if requested
        if extract_links:
            links = []
            for a in article.select("a[href]"):
                href = a.get("href", "")
                link_text = a.get_text(strip=True)
                if href.startswith("http") and link_text and len(link_text) > 5:
                    links.append(f"  - [{link_text}]({href})")

            if links:
                output += f"\n\n🔗 Enlaces encontrados ({len(links)}):\n"
                output += "\n".join(links[:20])

        log_operation("fetch_article", {"url": url}, f"{len(text)} chars")
        return output

    except Exception as e:
        return f"Error obteniendo artículo: {e}"



def _search_with_content_handler(query: str, max_chars: int = 3000, site: str = None) -> str:
    """Search Google and fetch content from first result."""
    try:
        # Search
        results = _google_search(query, max_results=3, site=site)

        if not results:
            return f"No se encontraron resultados para: {query}"

        output = f"🔍 Búsqueda: '{query}'\n\n"

        # Try to fetch first result with content
        first_result = None
        for r in results:
            if r.get("url") and r["url"].startswith("http"):
                first_result = r
                break

        if first_result:
            output += f"📄 **{first_result['title']}**\n"
            output += f"🌐 {first_result['url']}\n\n"

            # Fetch content
            try:
                if not is_safe_url(first_result["url"]):
                    output += "⚠️ URL bloqueada por seguridad (SSRF)\n"
                else:
                    import requests
                    from bs4 import BeautifulSoup

                    headers = {
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
                    }

                    response = requests.get(first_result["url"], headers=headers, timeout=10)
                    soup = BeautifulSoup(response.text, "lxml")

                    # Remove unwanted
                    for tag in soup.select("script, style, nav, footer, header, aside"):
                        tag.decompose()

                    # Find content
                    article = soup.select_one("article, main, [role='main']") or soup.body
                    if article:
                        text = article.get_text(separator="\n", strip=True)
                        import re
                        text = re.sub(r'\n{3,}', '\n\n', text)
                        output += text[:max_chars]
                    else:
                        output += first_result.get("snippet", "Sin contenido disponible")
            except Exception:
                output += first_result.get("snippet", "Error obteniendo contenido")
        else:
            # Just show snippets
            for i, r in enumerate(results, 1):
                output += f"{i}. **{r['title']}**\n"
                output += f"   {r.get('snippet', 'N/A')[:200]}\n\n"

        log_operation("search_with_content", {"query": query}, "OK")
        return output

    except Exception as e:
        return f"Error: {e}"


def _browse_web_handler(url: str, format: str = "text", timeout: int = 30) -> str:
    from mcp_common.security import is_safe_url
    if not is_safe_url(url):
        return "Error: URL no permitida (SSRF bloqueado — no se permiten IPs privadas o esquemas no seguros)"
    try:
        import httpx

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36"
        }

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers=headers)
            response.raise_for_status()

        if format == "json":
            try:
                import json as _json
                data = response.json()
                return _json.dumps(data, indent=2, ensure_ascii=False)
            except Exception:
                return f"No es JSON válido:\n{response.text[:2000]}"
        elif format == "html":
            return response.text[:5000]
        else:
            text = response.text
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
            text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
            text = re.sub(r'<[^>]+>', ' ', text)
            text = re.sub(r'\s+', ' ', text).strip()
            return text[:3000]

    except Exception as e:
        return f"Error obteniendo URL: {e}"


def _http_request_handler(url: str, method: str = "GET", headers: dict = None, body: str = None, timeout: int = 30) -> str:
    from mcp_common.security import is_safe_url
    if not is_safe_url(url):
        return "Error: URL no permitida (SSRF bloqueado — no se permiten IPs privadas o esquemas no seguros)"
    try:
        import httpx

        req_headers = headers or {}

        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            if method == "GET":
                response = client.get(url, headers=req_headers)
            elif method == "POST":
                response = client.post(url, headers=req_headers, content=body)
            elif method == "PUT":
                response = client.put(url, headers=req_headers, content=body)
            elif method == "DELETE":
                response = client.delete(url, headers=req_headers)
            elif method == "PATCH":
                response = client.patch(url, headers=req_headers, content=body)
            else:
                return f"Método no soportado: {method}"

            import json as _json
            safe_headers = {k: v for k, v in response.headers.items()
                           if k.lower() not in ("set-cookie", "authorization", "proxy-authorization")}
            result = {
                "status": response.status_code,
                "headers": safe_headers,
                "body": response.text[:5000]
            }

            log_operation("http_request", {"url": url, "method": method}, f"status:{response.status_code}")
            return _json.dumps(result, indent=2, ensure_ascii=False)

    except Exception as e:
        return f"Error HTTP: {e}"


# ── OSINT Implementations ───────────────────────────────────

HANDLERS = {
    "web_search": _web_search_handler,
    "search_google": _search_google_handler,
    "search_news": _search_news_handler,
    "search_docs": _search_docs_handler,
    "search_sports": _search_sports_handler,
    "fetch_article": _fetch_article_handler,
    "search_with_content": _search_with_content_handler,
    "browse_web": _browse_web_handler,
    "http_request": _http_request_handler,
}
