"""Fernet encryption for sensitive values (tokens, passwords, etc.)."""

import os
import base64
from mcp_common.paths import HOME

FERNET_KEY_PATH = os.path.join(HOME, ".local/share/chatmanager/secret_key")


def _get_fernet():
    """Get or create Fernet instance for encryption."""
    try:
        from cryptography.fernet import Fernet
        os.makedirs(os.path.dirname(FERNET_KEY_PATH), exist_ok=True)

        if os.path.exists(FERNET_KEY_PATH):
            with open(FERNET_KEY_PATH, "rb") as f:
                key = f.read().strip()
        else:
            key = Fernet.generate_key()
            with open(FERNET_KEY_PATH, "wb") as f:
                f.write(key)
            os.chmod(FERNET_KEY_PATH, 0o600)

        return Fernet(key)
    except ImportError:
        return None


def encrypt_value(value: str) -> str:
    """Encrypt a string value."""
    fernet = _get_fernet()
    if fernet:
        return fernet.encrypt(value.encode()).decode()
    return base64.b64encode(value.encode()).decode()


def decrypt_value(encrypted: str) -> str:
    """Decrypt a string value."""
    fernet = _get_fernet()
    if fernet:
        try:
            return fernet.decrypt(encrypted.encode()).decode()
        except Exception:
            pass
    try:
        return base64.b64decode(encrypted.encode()).decode()
    except Exception:
        return encrypted
