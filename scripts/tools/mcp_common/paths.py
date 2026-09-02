"""Shared paths, constants, and filesystem utilities."""

import os
import stat

HOME = os.path.expanduser("~")
BASE_DIR = HOME
MAX_OUTPUT_LINES = 500
MAX_FILE_SIZE = 1024 * 1024  # 1MB max read
COMMAND_TIMEOUT = 30


def safe_path(path: str) -> str:
    if not path:
        return BASE_DIR
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(BASE_DIR, path)
    return os.path.normpath(path)


def format_size(size_bytes: int) -> str:
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def format_permissions(mode: int) -> str:
    perms = ""
    for who in ['USR', 'GRP', 'OTH']:
        r = 'r' if mode & getattr(stat, f'S_I{who}READ') else '-'
        w = 'w' if mode & getattr(stat, f'S_I{who}WRITE') else '-'
        x = 'x' if mode & getattr(stat, f'S_I{who}EXEC') else '-'
        perms += r + w + x
    return perms
