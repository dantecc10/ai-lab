"""Spotify domain: playback control via spotify_player CLI."""

import os
import json
import subprocess

from mcp_common.paths import HOME
from mcp_common.logging import log_operation

SPOTIFY_PLAYER = os.path.join(HOME, ".cargo/bin/spotify_player")

TOOLS = [
    {
        "name": "spotify_search",
        "description": "Busca canciones, artistas o playlists en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Término de búsqueda."},
                "limit": {"type": "integer", "description": "Número de resultados. Default: 5."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "spotify_now",
        "description": "Muestra qué canción está sonando ahora en Spotify.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "spotify_play",
        "description": "Reanuda la reproducción en Spotify.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "spotify_pause",
        "description": "Pausa la reproducción en Spotify.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "spotify_next",
        "description": "Salta a la siguiente canción en Spotify.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "spotify_previous",
        "description": "Va a la canción anterior en Spotify.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "spotify_volume",
        "description": "Ajusta el volumen de Spotify (0-100).",
        "inputSchema": {
            "type": "object",
            "properties": {
                "level": {"type": "integer", "description": "Nivel de volumen (0-100)."}
            },
            "required": ["level"]
        }
    },
    {
        "name": "spotify_playlists",
        "description": "Lista tus playlists de Spotify.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "spotify_launch",
        "description": "Abre Spotify si no está corriendo.",
        "inputSchema": {"type": "object", "properties": {}}
    },
    {
        "name": "spotify_play_track",
        "description": "Busca y reproduce una canción específica en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Nombre de la canción."}
            },
            "required": ["query"]
        }
    },
    {
        "name": "spotify_play_artist",
        "description": "Reproduce música de un artista en Spotify.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "artist": {"type": "string", "description": "Nombre del artista."}
            },
            "required": ["artist"]
        }
    },
    {
        "name": "spotify_play_playlist",
        "description": "Reproduce una playlist de Spotify por nombre.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Nombre de la playlist."}
            },
            "required": ["name"]
        }
    },
]


# ── Handlers ───────────────────────────────────────────────

def _spotify_search(args):
    query = args["query"]
    limit = args.get("limit", 5)
    try:
        result = subprocess.run([SPOTIFY_PLAYER, "search", query], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"Error en búsqueda: {result.stderr}"
        data = json.loads(result.stdout)
        lines = [f"🔍 Resultados para '{query}':\n"]
        tracks = data.get("tracks", [])[:limit]
        for i, track in enumerate(tracks, 1):
            name = track.get("name", "Desconocido")
            artists = ", ".join(a.get("name", "") for a in track.get("artists", []))
            album = track.get("album", {}).get("name", "")
            lines.append(f"  {i}. {name} - {artists} ({album})")
        playlists = data.get("playlists", [])[:3]
        if playlists:
            lines.append(f"\n📋 Playlists:")
            for pl in playlists:
                lines.append(f"  - {pl.get('name', '')}")
        artists = data.get("artists", [])[:3]
        if artists:
            lines.append(f"\n👤 Artistas:")
            for a in artists:
                lines.append(f"  - {a.get('name', '')}")
        log_operation("spotify_search", {"query": query}, f"{len(tracks)} tracks")
        return "\n".join(lines)
    except json.JSONDecodeError:
        return "Error parseando resultados de Spotify"
    except FileNotFoundError:
        return f"Error: spotify_player no encontrado en {SPOTIFY_PLAYER}"
    except Exception as e:
        return f"Error en búsqueda Spotify: {e}"


def _spotify_now(args):
    try:
        result = subprocess.run([SPOTIFY_PLAYER, "get", "key", "current_playback"], capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return "No hay canción reproduciéndose actualmente"
        data = json.loads(result.stdout)
        if not data:
            return "No hay canción reproduciéndose actualmente"
        track = data.get("item", {})
        name = track.get("name", "Desconocido")
        artists = ", ".join(a.get("name", "") for a in track.get("artists", []))
        album = track.get("album", {}).get("name", "")
        is_playing = data.get("is_playing", False)
        progress = data.get("progress_ms", 0) // 1000
        duration = track.get("duration_ms", 0) // 1000
        status = "▶️ Reproduciendo" if is_playing else "⏸️ Pausado"
        log_operation("spotify_now", {}, name)
        return f"{status}: {name} - {artists}\nÁlbum: {album}\n{progress // 60}:{progress % 60:02d} / {duration // 60}:{duration % 60:02d}"
    except json.JSONDecodeError:
        return "Error parseando datos de Spotify"
    except Exception as e:
        return f"Error obteniendo estado: {e}"


def _spotify_play(args):
    subprocess.run([SPOTIFY_PLAYER, "playback", "play"], capture_output=True, text=True, timeout=10)
    log_operation("spotify_play", {}, "play")
    return "▶️ Reproduciendo en Spotify"


def _spotify_pause(args):
    subprocess.run([SPOTIFY_PLAYER, "playback", "pause"], capture_output=True, text=True, timeout=10)
    log_operation("spotify_pause", {}, "pause")
    return "⏸️ Spotify pausado"


def _spotify_next(args):
    subprocess.run([SPOTIFY_PLAYER, "playback", "next"], capture_output=True, text=True, timeout=10)
    log_operation("spotify_next", {}, "next")
    return "⏭️ Siguiente canción"


def _spotify_previous(args):
    subprocess.run([SPOTIFY_PLAYER, "playback", "previous"], capture_output=True, text=True, timeout=10)
    log_operation("spotify_previous", {}, "previous")
    return "⏮️ Canción anterior"


def _spotify_volume(args):
    level = max(0, min(100, args["level"]))
    subprocess.run([SPOTIFY_PLAYER, "playback", "volume", str(level)], capture_output=True, text=True, timeout=10)
    log_operation("spotify_volume", {"level": level}, "set")
    return f"🔊 Volumen Spotify: {level}%"


def _spotify_playlists(args):
    try:
        result = subprocess.run([SPOTIFY_PLAYER, "get", "key", "playlists"], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return "Error obteniendo playlists"
        data = json.loads(result.stdout)
        if not data:
            return "No se encontraron playlists"
        lines = ["📋 Tus playlists:\n"]
        items = data.get("items", [])[:20]
        for i, pl in enumerate(items, 1):
            name = pl.get("name", "Sin nombre")
            tracks = pl.get("tracks", {}).get("total", 0)
            lines.append(f"  {i}. {name} ({tracks} canciones)")
        log_operation("spotify_playlists", {}, f"{len(items)} playlists")
        return "\n".join(lines)
    except json.JSONDecodeError:
        return "Error parseando playlists"
    except Exception as e:
        return f"Error obteniendo playlists: {e}"


def _spotify_launch(args):
    try:
        result = subprocess.run(["pgrep", "-x", "spotify"], capture_output=True, text=True, timeout=5)
        if result.stdout.strip():
            return "Spotify ya está corriendo"
        subprocess.Popen(["spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        log_operation("spotify_launch", {}, "launched")
        return "🎵 Spotify abierto"
    except Exception as e:
        return f"Error abriendo Spotify: {e}"


def _spotify_play_track(args):
    query = args["query"]
    try:
        result = subprocess.run([SPOTIFY_PLAYER, "search", query], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"Error buscando: {result.stderr}"
        data = json.loads(result.stdout)
        tracks = data.get("tracks", [])
        if not tracks:
            return f"No encontré canciones para '{query}'"
        track = tracks[0]
        track_id = track.get("id", "")
        track_name = track.get("name", "")
        artists = ", ".join(a.get("name", "") for a in track.get("artists", []))
        subprocess.run([SPOTIFY_PLAYER, "playback", "start", "track", "--id", track_id], capture_output=True, text=True, timeout=10)
        log_operation("spotify_play_track", {"query": query}, track_name)
        return f"▶️ Reproduciendo: {track_name} - {artists}"
    except json.JSONDecodeError:
        return "Error parseando resultados"
    except Exception as e:
        return f"Error reproduciendo canción: {e}"


def _spotify_play_artist(args):
    artist = args["artist"]
    try:
        result = subprocess.run([SPOTIFY_PLAYER, "playback", "start", "context", "--name", artist], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"Error reproduciendo artista: {result.stderr}"
        log_operation("spotify_play_artist", {"artist": artist}, "playing")
        return f"▶️ Reproduciendo música de: {artist}"
    except Exception as e:
        return f"Error: {e}"


def _spotify_play_playlist(args):
    name = args["name"]
    try:
        result = subprocess.run([SPOTIFY_PLAYER, "playback", "start", "context", "--name", name], capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return f"Error reproduciendo playlist: {result.stderr}"
        log_operation("spotify_play_playlist", {"name": name}, "playing")
        return f"▶️ Reproduciendo playlist: {name}"
    except Exception as e:
        return f"Error: {e}"


HANDLERS = {
    "spotify_search": _spotify_search,
    "spotify_now": _spotify_now,
    "spotify_play": _spotify_play,
    "spotify_pause": _spotify_pause,
    "spotify_next": _spotify_next,
    "spotify_previous": _spotify_previous,
    "spotify_volume": _spotify_volume,
    "spotify_playlists": _spotify_playlists,
    "spotify_launch": _spotify_launch,
    "spotify_play_track": _spotify_play_track,
    "spotify_play_artist": _spotify_play_artist,
    "spotify_play_playlist": _spotify_play_playlist,
}
