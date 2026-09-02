#!/usr/bin/env bash
# AI Lab — Telegram Bot Controller Script

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
VENV="$REPO_ROOT/../scripting/gpu-tools/skills/.venv"
SERVICE_NAME="telegram-bot.service"

mkdir -p "$HOME/.config/ai-lab" "$HOME/.config/systemd/user"

# Colores
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BOLD='\033[1m'
NC='\033[0m'

function print_banner() {
    echo -e "${BLUE}${BOLD}"
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                🤖 AI Lab — Telegram Bot Control               ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

function install_service() {
    local svc_file="$HOME/.config/systemd/user/$SERVICE_NAME"
    cat <<EOF > "$svc_file"
[Unit]
Description=AI Lab Telegram Bot Service
After=network.target gemma4-server.service whisper-server.service

[Service]
Type=simple
WorkingDirectory=$REPO_ROOT
ExecStart=$VENV/bin/python -m scripts.telegram.bot
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment="PYTHONUNBUFFERED=1"
Environment="PATH=$VENV/bin:/usr/local/bin:/usr/bin:/bin"

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    echo -e "${GREEN}✓ Servicio systemd instalado en:${NC} $svc_file"
}

case "$1" in
    start)
        print_banner
        install_service
        systemctl --user enable --now "$SERVICE_NAME"
        echo -e "${GREEN}✓ Servicio $SERVICE_NAME iniciado.${NC}"
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    stop)
        systemctl --user stop "$SERVICE_NAME"
        echo -e "${YELLOW}✓ Servicio $SERVICE_NAME detenido.${NC}"
        ;;
    restart)
        install_service
        systemctl --user restart "$SERVICE_NAME"
        echo -e "${GREEN}✓ Servicio $SERVICE_NAME reiniciado.${NC}"
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    status)
        print_banner
        systemctl --user status "$SERVICE_NAME" --no-pager
        ;;
    logs)
        journalctl --user -u "$SERVICE_NAME" -f -n 50
        ;;
    run)
        print_banner
        echo -e "${BLUE}Ejecutando bot en primer plano...${NC}"
        export PYTHONPATH="$REPO_ROOT:$PYTHONPATH"
        exec "$VENV/bin/python" -m scripts.telegram.bot
        ;;
    set-token)
        if [ -z "$2" ]; then
            echo -e "${RED}Uso:${NC} $0 set-token <TELEGRAM_BOT_TOKEN>"
            exit 1
        fi
        PYTHONPATH="$REPO_ROOT" "$VENV/bin/python" -c "from scripts.telegram.config import save_token; save_token('$2')"
        echo -e "${GREEN}✓ Token de Telegram configurado exitosamente.${NC}"
        ;;
    allow-user)
        if [ -z "$2" ]; then
            echo -e "${RED}Uso:${NC} $0 allow-user <TELEGRAM_USER_ID>"
            exit 1
        fi
        PYTHONPATH="$REPO_ROOT" "$VENV/bin/python" -c "from scripts.telegram.config import add_allowed_user; add_allowed_user($2)"
        echo -e "${GREEN}✓ Usuario $2 añadido a la lista blanca.${NC}"
        ;;
    help|*)
        print_banner
        echo "Uso: $0 {start|stop|restart|status|logs|run|set-token|allow-user}"
        echo ""
        echo "Comandos:"
        echo "  start         Instala e inicia el bot como servicio en segundo plano (systemd)"
        echo "  stop          Detiene el servicio del bot"
        echo "  restart       Reinicia el servicio"
        echo "  status        Muestra el estado actual del servicio"
        echo "  logs          Muestra los registros en tiempo real"
        echo "  run           Ejecuta el bot directamente en la consola (modo debug)"
        echo "  set-token <t> Guarda el token de Telegram proporcionado por @BotFather"
        echo "  allow-user <u> Añade un ID de usuario a la lista blanca"
        echo ""
        ;;
esac
