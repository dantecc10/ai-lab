#!/bin/bash
# e4b-ctl — Controla el sub-agente E4B (CPU-only)
# Uso: ./e4b-ctl [start|stop|restart|status|logs]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

CONF_FILE="$HOME/.config/e4b-server.conf"
SERVICE="e4b-server.service"

# User-level systemd
if systemctl --user is-active "$SERVICE" &>/dev/null || systemctl --user is-enabled "$SERVICE" &>/dev/null 2>&1; then
    SYSCMD="systemctl --user"
else
    SYSCMD="systemctl"
fi

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }

do_start() {
    info "Iniciando E4B Sub-agent..."
    $SYSCMD daemon-reload
    $SYSCMD start "$SERVICE" 2>/dev/null || true
    sleep 3
    if $SYSCMD is-active "$SERVICE" &>/dev/null; then
        log "Sub-agente E4B iniciado"
        echo ""
        info "API: http://localhost:9091/v1"
        info "Web UI: http://localhost:9091"
    else
        err "Error al iniciar. Verifica: $SYSCMD status $SERVICE"
        $SYSCMD status "$SERVICE" --no-pager 2>/dev/null || true
    fi
}

do_stop() {
    info "Deteniendo E4B Sub-agent..."
    $SYSCMD stop "$SERVICE" 2>/dev/null || true
    log "Sub-agente detenido"
}

do_restart() {
    info "Reiniciando E4B Sub-agent..."
    $SYSCMD daemon-reload
    $SYSCMD restart "$SERVICE" 2>/dev/null || true
    sleep 3
    if $SYSCMD is-active "$SERVICE" &>/dev/null; then
        log "Sub-agente reiniciado"
    else
        err "Error al reiniciar"
    fi
}

do_status() {
    echo -e "\n${BOLD}${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  E4B Sub-agent — Estado${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════${NC}\n"

    # Service status
    if $SYSCMD is-active "$SERVICE" &>/dev/null; then
        log "Servicio: Activo"
    else
        warn "Servicio: Inactivo"
    fi

    # Config
    local ngl ctx port
    ngl=$(grep "^NGL=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "0")
    ctx=$(grep "^CTX_SIZE=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "8192")
    port=$(grep "^PORT=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "9091")

    echo ""
    info "Modelo: E4B (5GB, CPU-only)"
    info "NGL: $ngl (CPU)"
    info "CTX_SIZE: $ctx"
    info "Puerto: $port"

    # API check
    echo ""
    if curl -s "http://localhost:$port/v1/models" &>/dev/null; then
        log "API: http://localhost:$port ✓"
    else
        warn "API: No responde en puerto $port"
    fi

    # VRAM (should be 0 for CPU-only)
    echo ""
    info "VRAM GPU (debe ser 0 para CPU-only):"
    nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null || echo "  No disponible"
    echo ""
}

do_logs() {
    local lines="${1:-50}"
    $SYSCMD status "$SERVICE" --no-pager 2>/dev/null || true
    echo ""
    journalctl --user -u "$SERVICE" --no-pager -n "$lines" 2>/dev/null || \
    journalctl -u "$SERVICE" --no-pager -n "$lines" 2>/dev/null || \
    warn "No se pudieron obtener logs"
}

# ── Main ──────────────────────────────────────────────────
ACTION="${1:-}"
case "$ACTION" in
    start)    do_start ;;
    stop)     do_stop ;;
    restart)  do_restart ;;
    status)   do_status ;;
    logs)     do_logs "${2:-50}" ;;
    *)
        echo -e "${BOLD}e4b-ctl${NC} — Controla el sub-agente E4B (CPU-only)\n"
        echo "Uso: $0 <comando>"
        echo ""
        echo "Comandos:"
        echo "  start       Iniciar el sub-agente"
        echo "  stop        Detener el sub-agente"
        echo "  restart     Reiniciar el sub-agente"
        echo "  status      Ver estado completo"
        echo "  logs [n]    Ver últimos n logs (default: 50)"
        echo ""
        echo "El sub-agente E4B corre en CPU (puerto 9091)"
        echo "No usa VRAM, permitiendo al modelo principal usar más contexto."
        ;;
esac
