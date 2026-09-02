"""Sports & Football tools — BSD API (sports.bzzoiro.com) with token auth."""

import json
import os
from urllib.parse import quote
from mcp_common.logging import log_operation

BSD_BASE = "https://sports.bzzoiro.com/api/v2"
BSD_MCP = "https://sports.bzzoiro.com/mcp"


def _load_token():
    """Load API token from env var or config file."""
    token = os.environ.get("BSD_API_TOKEN", "")
    if token:
        return token
    token_file = os.path.expanduser("~/.config/sports-api/token")
    try:
        with open(token_file) as f:
            return f.read().strip()
    except Exception:
        return ""


BSD_TOKEN = _load_token()


def _bsd_request(path: str, params: dict = None) -> dict:
    """Make authenticated request to BSD API."""
    import requests
    url = f"{BSD_BASE}{path}"
    headers = {"Authorization": f"Token {BSD_TOKEN}"}
    resp = requests.get(url, headers=headers, params=params or {}, timeout=15)
    resp.raise_for_status()
    return resp.json()


TOOLS = [
    # ── Matches ────────────────────────────────────────────
    {
        "name": "football_search_matches",
        "description": "Buscar partidos de fútbol por equipos, ligas o fechas. Retorna IDs para usar con get_match_detail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nombre del equipo, liga o búsqueda (ej: 'Barcelona', 'Premier League', 'hoy')"},
                "live_only": {"type": "boolean", "description": "Solo partidos en vivo", "default": False},
                "limit": {"type": "integer", "description": "Número máximo de resultados (default 10)", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "football_get_match",
        "description": "Detalle completo de un partido: goles, alineaciones, estadísticas, posesión, tiros, xG, odds, predicción IA, y enfrentamientos directos (h2h).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "integer", "description": "ID del partido (obtener de search_matches)"}
            },
            "required": ["match_id"]
        }
    },
    {
        "name": "football_live_scores",
        "description": "Scores en vivo de todos los partidos que están jugándose ahora. Ideal para seguir resultados en tiempo real.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Número máximo de partidos (default 50)", "default": 50}
            }
        }
    },
    {
        "name": "football_get_match_h2h",
        "description": "Historial de enfrentamientos directos entre dos equipos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "integer", "description": "ID del partido"}
            },
            "required": ["match_id"]
        }
    },
    {
        "name": "football_get_match_lineups",
        "description": "Alineaciones titulares y suplentes de un partido.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "integer", "description": "ID del partido"}
            },
            "required": ["match_id"]
        }
    },
    {
        "name": "football_get_match_shotmap",
        "description": "Mapa de tiros con xG de cada disparo. Muestra posición y calidad de las ocasiones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "integer", "description": "ID del partido"}
            },
            "required": ["match_id"]
        }
    },
    {
        "name": "football_get_match_incidents",
        "description": "Todos los incidentes del partido: goles, tarjetas, sustituciones, penales, VAR.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "integer", "description": "ID del partido"}
            },
            "required": ["match_id"]
        }
    },
    # ── Teams & Players ────────────────────────────────────
    {
        "name": "football_search_teams",
        "description": "Buscar equipos por nombre. Retorna IDs para usar con get_team_detail.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nombre del equipo"},
                "limit": {"type": "integer", "description": "Máximo de resultados (default 10)", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "football_get_team",
        "description": "Detalle completo del equipo: plantilla, estadísticas, fixtures próximos, transferencias.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer", "description": "ID del equipo (obtener de search_teams)"}
            },
            "required": ["team_id"]
        }
    },
    {
        "name": "football_get_team_fixtures",
        "description": "Próximos partidos y resultados recientes de un equipo.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "team_id": {"type": "integer", "description": "ID del equipo"},
                "limit": {"type": "integer", "description": "Número de partidos (default 10)", "default": 10}
            },
            "required": ["team_id"]
        }
    },
    {
        "name": "football_search_players",
        "description": "Buscar jugadores por nombre. Retorna IDs para usar con get_player.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nombre del jugador"},
                "limit": {"type": "integer", "description": "Máximo de resultados (default 10)", "default": 10}
            },
            "required": ["query"]
        }
    },
    {
        "name": "football_get_player",
        "description": "Detalle completo del jugador: posición, equipo actual, estadísticas, career history, valor de mercado.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "player_id": {"type": "integer", "description": "ID del jugador (obtener de search_players)"}
            },
            "required": ["player_id"]
        }
    },
    {
        "name": "football_get_player_stats",
        "description": "Estadísticas detalladas del jugador: goles, asistencias, minutos jugados, rating.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "player_id": {"type": "integer", "description": "ID del jugador"}
            },
            "required": ["player_id"]
        }
    },
    # ── Leagues & Standings ────────────────────────────────
    {
        "name": "football_list_leagues",
        "description": "Listar todas las ligas disponibles: Premier League, La Liga, Bundesliga, Serie A, Ligue 1, Champions, etc.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "country": {"type": "string", "description": "Filtrar por país (opcional)"}
            }
        }
    },
    {
        "name": "football_get_standings",
        "description": "Tabla de posiciones de una liga: puntos, partidos jugados, ganados, empatados, perdidos, goles, diferencia de goles.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "integer", "description": "ID de la liga (obtener de list_leagues)"},
                "season": {"type": "string", "description": "Temporada (ej: '2025', '2024-2025'). Default: actual."}
            },
            "required": ["league_id"]
        }
    },
    {
        "name": "football_list_seasons",
        "description": "Listar temporadas disponibles para una liga.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "league_id": {"type": "integer", "description": "ID de la liga"}
            },
            "required": ["league_id"]
        }
    },
    # ── Odds & Predictions ─────────────────────────────────
    {
        "name": "football_compare_odds",
        "description": "Comparar cuotas de múltiples casas de apuestas para un partido.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "integer", "description": "ID del partido"}
            },
            "required": ["match_id"]
        }
    },
    {
        "name": "football_get_predictions",
        "description": "Predicciones ML del modelo CatBoost: probabilidades de resultado, goles totales, ambos equipos anotan.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "match_id": {"type": "integer", "description": "ID del partido"}
            },
            "required": ["match_id"]
        }
    },
    # ── Info ───────────────────────────────────────────────
    {
        "name": "football_list_venues",
        "description": "Listar estadios de fútbol con capacidad y ubicación.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Máximo (default 50)", "default": 50}
            }
        }
    },
    {
        "name": "football_list_referees",
        "description": "Listar árbitros activos con estadísticas de tarjetas y penales.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Máximo (default 50)", "default": 50}
            }
        }
    },
]


# ── Handlers ──────────────────────────────────────────────

def _football_search_matches_handler(query: str, live_only: bool = False, limit: int = 10) -> str:
    try:
        params = {"search": query, "limit": min(limit, 50)}
        if live_only:
            data = _bsd_request("/events/live/", params)
        else:
            data = _bsd_request("/events/", params)
        results = data.get("results", data) if isinstance(data, dict) else data
        if not results:
            return f"No se encontraron partidos para: {query}"
        output = f"⚽ **{len(results)} partidos encontrados para '{query}':**\n\n"
        for m in results[:limit]:
            home = m.get("home_team", {}).get("name", "?")
            away = m.get("away_team", {}).get("name", "?")
            score = m.get("score", {})
            status = m.get("status", "")
            time_str = m.get("date", "")[:16]
            if score:
                score_str = f"{score.get('home', '?')}-{score.get('away', '?')}"
            else:
                score_str = "vs"
            output += f"• **{home} {score_str} {away}** | {status} | {time_str} | ID: {m.get('id', '?')}\n"
        log_operation("football_search_matches", {"query": query}, f"{len(results)} results")
        return output
    except Exception as e:
        return f"Error buscando partidos: {e}"


def _football_get_match_handler(match_id: int) -> str:
    try:
        data = _bsd_request(f"/events/{match_id}/")
        home = data.get("home_team", {}).get("name", "?")
        away = data.get("away_team", {}).get("name", "?")
        score = data.get("score", {})
        status = data.get("status", "")
        league = data.get("league", {}).get("name", "?")
        date = data.get("date", "")[:16]
        stats = data.get("statistics", {})
        prediction = data.get("prediction", {})
        output = f"⚽ **{home} {score.get('home', '?')} - {score.get('away', '?')} {away}**\n"
        output += f"🏆 {league} | {status} | {date}\n\n"
        if stats:
            output += "**📊 Estadísticas:**\n"
            for key, val in stats.items():
                output += f"• {key}: {val}\n"
            output += "\n"
        if prediction:
            output += f"🤖 **Predicción IA:** {json.dumps(prediction, ensure_ascii=False)[:300]}\n"
        log_operation("football_get_match", {"match_id": match_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo partido: {e}"


def _football_live_scores_handler(limit: int = 50) -> str:
    try:
        data = _bsd_request("/events/live/", {"limit": min(limit, 200)})
        results = data.get("results", data) if isinstance(data, dict) else data
        if not results:
            return "No hay partidos en vivo ahora mismo."
        output = f"🔴 **{len(results)} partidos en vivo:**\n\n"
        for m in results[:limit]:
            home = m.get("home_team", {}).get("name", "?")
            away = m.get("away_team", {}).get("name", "?")
            score = m.get("score", {})
            minute = m.get("minute", "?")
            output += f"• **{home} {score.get('home', '?')}-{score.get('away', '?')} {away}** ({minute}') | ID: {m.get('id', '?')}\n"
        log_operation("football_live_scores", {}, f"{len(results)} live")
        return output
    except Exception as e:
        return f"Error obteniendo live scores: {e}"


def _football_get_match_h2h_handler(match_id: int) -> str:
    try:
        data = _bsd_request(f"/events/{match_id}/h2h/")
        output = f"📊 **Enfrentamientos directos (ID: {match_id}):**\n\n"
        for h in (data if isinstance(data, list) else data.get("results", [])):
            output += f"• {h.get('date', '')[:10]} | {h.get('home_team', {}).get('name', '?')} {h.get('score', {}).get('home', '?')}-{h.get('score', {}).get('away', '?')} {h.get('away_team', {}).get('name', '?')}\n"
        log_operation("football_get_match_h2h", {"match_id": match_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo h2h: {e}"


def _football_get_match_lineups_handler(match_id: int) -> str:
    try:
        data = _bsd_request(f"/events/{match_id}/lineups/")
        output = f"👥 **Alineaciones (ID: {match_id}):**\n\n"
        for team_key in ["home", "away"]:
            team_data = data.get(team_key, {})
            team_name = team_data.get("team", {}).get("name", team_key.upper())
            output += f"**{team_name}:**\n"
            for p in team_data.get("players", []):
                output += f"  {p.get('position', '?')} #{p.get('shirt_number', '?')} {p.get('name', '?')}\n"
        log_operation("football_get_match_lineups", {"match_id": match_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo alineaciones: {e}"


def _football_get_match_shotmap_handler(match_id: int) -> str:
    try:
        data = _bsd_request(f"/events/{match_id}/shotmap/")
        output = f"🎯 **Mapa de tiros (ID: {match_id}):**\n\n"
        for shot in (data if isinstance(data, list) else data.get("shots", [])):
            xg = shot.get("xg", "?")
            result = shot.get("result", "?")
            player = shot.get("player", {}).get("name", "?")
            output += f"• {player} | xG: {xg} | Resultado: {result}\n"
        log_operation("football_get_match_shotmap", {"match_id": match_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo shotmap: {e}"


def _football_get_match_incidents_handler(match_id: int) -> str:
    try:
        data = _bsd_request(f"/events/{match_id}/incidents/")
        output = f"📋 **Incidentes (ID: {match_id}):**\n\n"
        for inc in (data if isinstance(data, list) else data.get("incidents", [])):
            minute = inc.get("minute", "?")
            itype = inc.get("type", "?")
            player = inc.get("player", {}).get("name", "?")
            detail = inc.get("detail", "")
            output += f"• {minute}' {itype} - {player} {detail}\n"
        log_operation("football_get_match_incidents", {"match_id": match_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo incidentes: {e}"


def _football_search_teams_handler(query: str, limit: int = 10) -> str:
    try:
        data = _bsd_request("/teams/", {"search": query, "limit": min(limit, 50)})
        results = data.get("results", data) if isinstance(data, dict) else data
        if not results:
            return f"No se encontraron equipos para: {query}"
        output = f"🏟️ **{len(results)} equipos encontrados para '{query}':**\n\n"
        for t in results[:limit]:
            output += f"• **{t.get('name', '?')}** | País: {t.get('country', {}).get('name', '?')} | ID: {t.get('id', '?')}\n"
        log_operation("football_search_teams", {"query": query}, f"{len(results)} results")
        return output
    except Exception as e:
        return f"Error buscando equipos: {e}"


def _football_get_team_handler(team_id: int) -> str:
    try:
        data = _bsd_request(f"/teams/{team_id}/")
        output = f"🏟️ **{data.get('name', '?')}**\n"
        output += f"País: {data.get('country', {}).get('name', '?')}\n"
        if data.get("venue"):
            output += f"Estadio: {data['venue'].get('name', '?')} ({data['venue'].get('capacity', '?')} personas)\n"
        log_operation("football_get_team", {"team_id": team_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo equipo: {e}"


def _football_get_team_fixtures_handler(team_id: int, limit: int = 10) -> str:
    try:
        data = _bsd_request(f"/teams/{team_id}/fixtures/", {"limit": min(limit, 50)})
        results = data.get("results", data) if isinstance(data, dict) else data
        output = f"📅 **Fixtures del equipo (ID: {team_id}):**\n\n"
        for m in results[:limit]:
            home = m.get("home_team", {}).get("name", "?")
            away = m.get("away_team", {}).get("name", "?")
            date = m.get("date", "")[:16]
            output += f"• {date} | {home} vs {away}\n"
        log_operation("football_get_team_fixtures", {"team_id": team_id}, f"{len(results)} fixtures")
        return output
    except Exception as e:
        return f"Error obteniendo fixtures: {e}"


def _football_search_players_handler(query: str, limit: int = 10) -> str:
    try:
        data = _bsd_request("/players/", {"search": query, "limit": min(limit, 50)})
        results = data.get("results", data) if isinstance(data, dict) else data
        if not results:
            return f"No se encontraron jugadores para: {query}"
        output = f"👤 **{len(results)} jugadores encontrados para '{query}':**\n\n"
        for p in results[:limit]:
            pos = p.get("position", "?")
            team = p.get("team", {}).get("name", "?")
            output += f"• **{p.get('name', '?')}** | {pos} | {team} | ID: {p.get('id', '?')}\n"
        log_operation("football_search_players", {"query": query}, f"{len(results)} results")
        return output
    except Exception as e:
        return f"Error buscando jugadores: {e}"


def _football_get_player_handler(player_id: int) -> str:
    try:
        data = _bsd_request(f"/players/{player_id}/")
        output = f"👤 **{data.get('name', '?')}**\n"
        output += f"Posición: {data.get('position', '?')}\n"
        output += f"Equipo: {data.get('team', {}).get('name', '?')}\n"
        output += f"País: {data.get('country', {}).get('name', '?')}\n"
        if data.get("date_of_birth"):
            output += f"Nacimiento: {data['date_of_birth'][:10]}\n"
        if data.get("market_value"):
            output += f"Valor de mercado: {data['market_value']}\n"
        log_operation("football_get_player", {"player_id": player_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo jugador: {e}"


def _football_get_player_stats_handler(player_id: int) -> str:
    try:
        data = _bsd_request(f"/players/{player_id}/stats/")
        output = f"📊 **Estadísticas del jugador (ID: {player_id}):**\n\n"
        output += json.dumps(data, ensure_ascii=False, indent=2)[:2000]
        log_operation("football_get_player_stats", {"player_id": player_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo estadísticas: {e}"


def _football_list_leagues_handler(country: str = "") -> str:
    try:
        params = {}
        if country:
            params["country"] = country
        data = _bsd_request("/leagues/", params)
        results = data.get("results", data) if isinstance(data, dict) else data
        output = f"🏆 **Ligas disponibles:**\n\n"
        for l in results[:50]:
            output += f"• **{l.get('name', '?')}** | {l.get('country', {}).get('name', '?')} | ID: {l.get('id', '?')}\n"
        log_operation("football_list_leagues", {"country": country}, f"{len(results)} leagues")
        return output
    except Exception as e:
        return f"Error listando ligas: {e}"


def _football_get_standings_handler(league_id: int, season: str = "") -> str:
    try:
        params = {}
        if season:
            params["season"] = season
        data = _bsd_request(f"/leagues/{league_id}/standings/", params)
        league_name = data.get("league_name", f"Liga ID: {league_id}")
        season_info = data.get("season", {}).get("name", "")
        standings = data.get("standings", [])
        output = f"📊 **Tabla de posiciones — {league_name} ({season_info}):**\n\n"
        output += f"{'#':<4} {'Equipo':<25} {'PJ':<4} {'G':<4} {'E':<4} {'P':<4} {'GF':<4} {'GC':<4} {'DG':<4} {'Pts':<4} {'Forma':<8}\n"
        output += "-" * 90 + "\n"
        for row in standings:
            pos = row.get("position", "?")
            team = row.get("team_name", "?")[:24]
            played = row.get("played", 0)
            won = row.get("won", 0)
            drawn = row.get("drawn", 0)
            lost = row.get("lost", 0)
            gf = row.get("gf", 0)
            ga = row.get("ga", 0)
            gd = row.get("gd", 0)
            pts = row.get("pts", 0)
            form = row.get("form", "")[:7]
            output += f"{pos:<4} {team:<25} {played:<4} {won:<4} {drawn:<4} {lost:<4} {gf:<4} {ga:<4} {gd:<4} {pts:<4} {form:<8}\n"
        # Zones info
        zones = data.get("zones", [])
        if zones:
            output += "\n**Zonas:** "
            output += " | ".join(f"{z.get('label', '?')} ({z.get('from', '?')}-{z.get('to', '?')})" for z in zones)
            output += "\n"
        log_operation("football_get_standings", {"league_id": league_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo posiciones: {e}"


def _football_list_seasons_handler(league_id: int) -> str:
    try:
        data = _bsd_request(f"/leagues/{league_id}/seasons/")
        output = f"📅 **Temporadas (Liga ID: {league_id}):**\n\n"
        for s in (data if isinstance(data, list) else data.get("seasons", [])):
            output += f"• {s.get('name', '?')} | ID: {s.get('id', '?')}\n"
        log_operation("football_list_seasons", {"league_id": league_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo temporadas: {e}"


def _football_compare_odds_handler(match_id: int) -> str:
    try:
        data = _bsd_request(f"/events/{match_id}/odds/")
        output = f"💰 **Cuotas (ID: {match_id}):**\n\n"
        for bookmaker in (data if isinstance(data, list) else data.get("bookmakers", [])):
            name = bookmaker.get("name", "?")
            markets = bookmaker.get("markets", [])
            output += f"**{name}:**\n"
            for m in markets:
                output += f"  {m.get('name', '?')}: "
                for o in m.get("outcomes", []):
                    output += f"{o.get('name', '?')} @{o.get('price', '?')}  "
                output += "\n"
        log_operation("football_compare_odds", {"match_id": match_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo cuotas: {e}"


def _football_get_predictions_handler(match_id: int) -> str:
    try:
        data = _bsd_request(f"/events/{match_id}/predictions/")
        output = f"🤖 **Predicciones IA (ID: {match_id}):**\n\n"
        output += json.dumps(data, ensure_ascii=False, indent=2)[:2000]
        log_operation("football_get_predictions", {"match_id": match_id}, "OK")
        return output
    except Exception as e:
        return f"Error obteniendo predicciones: {e}"


def _football_list_venues_handler(limit: int = 50) -> str:
    try:
        data = _bsd_request("/venues/", {"limit": min(limit, 200)})
        results = data.get("results", data) if isinstance(data, dict) else data
        output = f"🏟️ **Estadios:**\n\n"
        for v in results[:limit]:
            output += f"• **{v.get('name', '?')}** | {v.get('city', '?')} | Cap: {v.get('capacity', '?')} | ID: {v.get('id', '?')}\n"
        log_operation("football_list_venues", {}, f"{len(results)} venues")
        return output
    except Exception as e:
        return f"Error listando estadios: {e}"


def _football_list_referees_handler(limit: int = 50) -> str:
    try:
        data = _bsd_request("/referees/", {"limit": min(limit, 200)})
        results = data.get("results", data) if isinstance(data, dict) else data
        output = f"👨‍⚖️ **Árbitros:**\n\n"
        for r in results[:limit]:
            output += f"• **{r.get('name', '?')}** | País: {r.get('country', {}).get('name', '?')} | ID: {r.get('id', '?')}\n"
        log_operation("football_list_referees", {}, f"{len(results)} referees")
        return output
    except Exception as e:
        return f"Error listando árbitros: {e}"


HANDLERS = {
    "football_search_matches": _football_search_matches_handler,
    "football_get_match": _football_get_match_handler,
    "football_live_scores": _football_live_scores_handler,
    "football_get_match_h2h": _football_get_match_h2h_handler,
    "football_get_match_lineups": _football_get_match_lineups_handler,
    "football_get_match_shotmap": _football_get_match_shotmap_handler,
    "football_get_match_incidents": _football_get_match_incidents_handler,
    "football_search_teams": _football_search_teams_handler,
    "football_get_team": _football_get_team_handler,
    "football_get_team_fixtures": _football_get_team_fixtures_handler,
    "football_search_players": _football_search_players_handler,
    "football_get_player": _football_get_player_handler,
    "football_get_player_stats": _football_get_player_stats_handler,
    "football_list_leagues": _football_list_leagues_handler,
    "football_get_standings": _football_get_standings_handler,
    "football_list_seasons": _football_list_seasons_handler,
    "football_compare_odds": _football_compare_odds_handler,
    "football_get_predictions": _football_get_predictions_handler,
    "football_list_venues": _football_list_venues_handler,
    "football_list_referees": _football_list_referees_handler,
}
