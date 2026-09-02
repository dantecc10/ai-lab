#!/usr/bin/env python3
"""
Cloudflare R2 Storage Manager — AI Lab
Manejo de almacenamiento de objetos S3/R2 para multimedia (imágenes, audio, video, archivos).
"""

import os
import sys
import json
import uuid
import mimetypes
from pathlib import Path
from typing import Optional, Dict, Any, List

# Rutas de configuración
CONFIG_DIR = Path.home() / ".config" / "ai-lab"
ENV_FILE = CONFIG_DIR / "r2.env"


def _load_env_file():
    """Carga variables desde ~/.config/ai-lab/r2.env si existe."""
    if ENV_FILE.exists():
        try:
            with open(ENV_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k not in os.environ:
                            os.environ[k] = v
        except Exception:
            pass


_load_env_file()


class R2Storage:
    def __init__(
        self,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        bucket_name: Optional[str] = None,
        public_domain: Optional[str] = None
    ):
        self.account_id = account_id or os.getenv("R2_ACCOUNT_ID", "")
        self.access_key_id = access_key_id or os.getenv("R2_ACCESS_KEY_ID", "")
        self.secret_access_key = secret_access_key or os.getenv("R2_SECRET_ACCESS_KEY", "")
        self.bucket_name = bucket_name or os.getenv("R2_BUCKET_NAME", "ai-chat-media")
        
        # Dominio público (ej: https://pub-xxxx.r2.dev o https://media.castelancarpinteyro.com)
        pub = public_domain or os.getenv("R2_PUBLIC_DOMAIN", "")
        if pub and not pub.startswith("http"):
            pub = f"https://{pub}"
        self.public_domain = pub.rstrip("/") if pub else ""

        self._client = None

    @property
    def is_configured(self) -> bool:
        return bool(self.account_id and self.access_key_id and self.secret_access_key and self.bucket_name)

    def get_client(self):
        if self._client is not None:
            return self._client

        if not self.is_configured:
            raise ValueError(
                "Cloudflare R2 no está configurado. Define R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY y R2_BUCKET_NAME en ~/.config/ai-lab/r2.env o variables de entorno."
            )

        import boto3
        from botocore.config import Config

        endpoint_url = f"https://{self.account_id}.r2.cloudflarestorage.com"
        self._client = boto3.client(
            "s3",
            endpoint_url=endpoint_url,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            region_name="auto",
            config=Config(s3={"addressing_style": "path"}, signature_version="s3v4")
        )
        return self._client

    def get_public_url(self, key: str) -> str:
        """Genera la URL pública para una clave dada."""
        key = key.lstrip("/")
        if self.public_domain:
            return f"{self.public_domain}/{key}"
        # Fallback genérico a endpoint R2
        return f"https://{self.bucket_name}.{self.account_id}.r2.cloudflarestorage.com/{key}"

    def upload_file(
        self,
        local_path: str,
        key: Optional[str] = None,
        prefix: str = "media",
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sube un archivo local a Cloudflare R2 y retorna sus metadatos y URL pública."""
        p = Path(local_path)
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Archivo no encontrado: {local_path}")

        if not key:
            ext = p.suffix.lower()
            random_id = uuid.uuid4().hex[:12]
            safe_stem = "".join(c for c in p.stem if c.isalnum() or c in ("-", "_"))[:30] or "asset"
            key = f"{prefix}/{safe_stem}_{random_id}{ext}"

        if not content_type:
            mime, _ = mimetypes.guess_type(str(p))
            content_type = mime or "application/octet-stream"

        file_size = p.stat().st_size

        client = self.get_client()
        with open(p, "rb") as f:
            client.put_object(
                Bucket=self.bucket_name,
                Key=key,
                Body=f,
                ContentType=content_type,
                CacheControl="public, max-age=31536000, immutable"
            )

        public_url = self.get_public_url(key)
        return {
            "key": key,
            "url": public_url,
            "size": file_size,
            "content_type": content_type,
            "filename": p.name
        }

    def upload_bytes(
        self,
        data: bytes,
        filename: str,
        prefix: str = "media",
        content_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Sube bytes en memoria (audios generados, capturas de pantalla, etc.) a Cloudflare R2."""
        ext = Path(filename).suffix.lower()
        if not content_type:
            mime, _ = mimetypes.guess_type(filename)
            content_type = mime or "application/octet-stream"

        random_id = uuid.uuid4().hex[:12]
        safe_stem = "".join(c for c in Path(filename).stem if c.isalnum() or c in ("-", "_"))[:30] or "asset"
        key = f"{prefix}/{safe_stem}_{random_id}{ext}"

        client = self.get_client()
        client.put_object(
            Bucket=self.bucket_name,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable"
        )

        public_url = self.get_public_url(key)
        return {
            "key": key,
            "url": public_url,
            "size": len(data),
            "content_type": content_type,
            "filename": filename
        }

    def list_files(self, prefix: str = "", max_keys: int = 50) -> List[Dict[str, Any]]:
        """Lista archivos almacenados en el bucket."""
        client = self.get_client()
        resp = client.list_objects_v2(
            Bucket=self.bucket_name,
            Prefix=prefix,
            MaxKeys=max_keys
        )

        results = []
        for item in resp.get("Contents", []):
            results.append({
                "key": item["Key"],
                "size": item["Size"],
                "last_modified": item["LastModified"].isoformat(),
                "url": self.get_public_url(item["Key"])
            })
        return results

    def delete_file(self, key: str) -> bool:
        """Elimina un archivo de R2."""
        client = self.get_client()
        client.delete_object(Bucket=self.bucket_name, Key=key)
        return True


# Instancia singleton por defecto
r2 = R2Storage()


def save_r2_config(
    account_id: str,
    access_key_id: str,
    secret_access_key: str,
    bucket_name: str,
    public_domain: str = ""
) -> str:
    """Guarda la configuración de R2 en ~/.config/ai-lab/r2.env."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    content = f"""# Cloudflare R2 Storage Configuration — AI Lab
R2_ACCOUNT_ID="{account_id}"
R2_ACCESS_KEY_ID="{access_key_id}"
R2_SECRET_ACCESS_KEY="{secret_access_key}"
R2_BUCKET_NAME="{bucket_name}"
R2_PUBLIC_DOMAIN="{public_domain}"
"""
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write(content)
    os.chmod(ENV_FILE, 0o600)
    _load_env_file()
    return f"Configuración de R2 guardada correctamente en {ENV_FILE}"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Gestor de Almacenamiento Cloudflare R2")
    sub = parser.add_subparsers(dest="action")

    # upload
    p_up = sub.add_parser("upload", help="Subir un archivo a R2")
    p_up.add_argument("file", help="Ruta al archivo local")
    p_up.add_argument("--prefix", default="media", help="Prefijo de carpeta en R2")

    # list
    p_ls = sub.add_parser("list", help="Listar archivos en R2")
    p_ls.add_argument("--prefix", default="", help="Prefijo a filtrar")
    p_ls.add_argument("--limit", type=int, default=20, help="Límite")

    # configure
    p_cfg = sub.add_parser("configure", help="Configurar credenciales de R2")
    p_cfg.add_argument("--account-id", required=True, help="Cloudflare Account ID")
    p_cfg.add_argument("--access-key", required=True, help="Access Key ID")
    p_cfg.add_argument("--secret-key", required=True, help="Secret Access Key")
    p_cfg.add_argument("--bucket", required=True, help="Nombre del Bucket")
    p_cfg.add_argument("--public-domain", default="", help="Dominio público (ej: media.castelancarpinteyro.com)")

    # status
    p_st = sub.add_parser("status", help="Comprobar estado de conexión con R2")

    args = parser.parse_args()

    if args.action == "configure":
        msg = save_r2_config(args.account_id, args.access_key, args.secret_key, args.bucket, args.public_domain)
        print(f"✅ {msg}")
    elif args.action == "upload":
        storage = R2Storage()
        res = storage.upload_file(args.file, prefix=args.prefix)
        print(f"✅ Archivo subido con éxito:")
        print(f"🌐 URL Pública: {res['url']}")
        print(f"🔑 Key:        {res['key']}")
        print(f"📦 Tamaño:     {res['size']} bytes")
    elif args.action == "list":
        storage = R2Storage()
        items = storage.list_files(prefix=args.prefix, max_keys=args.limit)
        print(f"📂 Archivos en R2 ({len(items)}):")
        for it in items:
            print(f"• {it['key']} ({it['size']} bytes) -> {it['url']}")
    elif args.action == "status":
        storage = R2Storage()
        if not storage.is_configured:
            print("⚠️ Cloudflare R2 no está configurado.")
            print(f"Crea o edita {ENV_FILE} o ejecuta: python3 r2_storage.py configure --help")
        else:
            try:
                items = storage.list_files(max_keys=1)
                print(f"🟢 Conexión a Cloudflare R2 exitosa (Bucket: {storage.bucket_name})")
                if storage.public_domain:
                    print(f"🌐 Dominio Público: {storage.public_domain}")
            except Exception as e:
                print(f"🔴 Error conectando a R2: {e}")
    else:
        parser.print_help()
