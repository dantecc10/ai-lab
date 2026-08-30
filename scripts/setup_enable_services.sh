#!/usr/bin/env bash
set -euo pipefail

# Script helper para copiar unidades systemd de `configs/systemd/`
# y habilitarlas como servicios de usuario, además de activar linger.

USER_HOME=${HOME:-/home/darkseid}

echo "Copiando unidades systemd al directorio de usuario..."
mkdir -p "$USER_HOME/.config/systemd/user"
cp configs/systemd/*.service "$USER_HOME/.config/systemd/user/"

echo "Recargando demonio systemd de usuario..."
systemctl --user daemon-reload

echo "Habilitando servicios: gemma4, e4b, whisper, chatmanager"
systemctl --user enable --now gemma4-server.service e4b-server.service whisper-server.service chatmanager.service

echo "Habilitando linger para el usuario (requiere sudo)..."
echo "Ejecuta: sudo loginctl enable-linger $USER"

echo "Si usas Docker para Open WebUI, asegúrate de habilitar docker:" \
     "sudo systemctl enable --now docker"

echo "Listo. Comprueba el estado con: systemctl --user status gemma4-server.service"
