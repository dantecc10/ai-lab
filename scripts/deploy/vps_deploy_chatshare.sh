#!/usr/bin/env bash
set -euo pipefail

# Despliega ChatShare en /opt/ai-chat usando Docker Compose.
# Escucha en 127.0.0.1:9095 (sin exponer puertos públicos comunes ni tocar Nginx de Plesk).

DEST=/opt/ai-chat
REPO=https://github.com/dantecc10/ai-lab.git
CONTAINER_NAME=chatshare
PORT_LOCAL=9095

echo "[+] Creando/verificando directorio de destino: $DEST"
mkdir -p "$DEST"
cd "$DEST"

if ! command -v docker >/dev/null 2>&1; then
  echo "[!] Docker no encontrado. Instalando docker..."
  apt-get update
  apt-get install -y docker.io docker-compose-v2
  systemctl enable --now docker
fi

if [ ! -d "$DEST/.git" ]; then
  echo "[+] Clonando repositorio $REPO en $DEST"
  git clone "$REPO" .
else
  echo "[+] Repositorio existente en $DEST, sincronizando..."
  git -C "$DEST" fetch --all
  git -C "$DEST" reset --hard origin/main
fi

# Eliminar contenedor legado en caso de existir
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
  echo "[+] Deteniendo y removiendo contenedor existente $CONTAINER_NAME"
  docker rm -f "$CONTAINER_NAME" || true
fi

# Limpiar carpeta build temporal antigua si existe
rm -rf "$DEST/build_chatshare"

echo "[+] Construyendo y levantando servicios con Docker Compose..."
cd "$DEST/deploy/chatshare"

docker compose down || true
docker compose up -d --build

echo "[+] Verificando estado del contenedor..."
sleep 3
if curl -sf "http://127.0.0.1:${PORT_LOCAL}/health" >/dev/null; then
  echo "[✓] ChatShare desplegado con éxito y respondiendo en 127.0.0.1:${PORT_LOCAL}/health"
else
  echo "[!] Advertencia: No se recibió respuesta inmediata de salud. Ver logs con: docker logs $CONTAINER_NAME"
fi
