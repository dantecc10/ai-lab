#!/bin/bash
# gemma4-ctl — Controla el servicio Gemma 4 AI Server
# Uso: ./gemma4-ctl [start|stop|restart|status|logs|switch|list]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

CONF_FILE="$HOME/.config/gemma4-server.conf"
SERVICE="gemma4-server.service"

# User-level systemd (check if running as user service)
if systemctl --user is-active "$SERVICE" &>/dev/null || systemctl --user is-enabled "$SERVICE" &>/dev/null 2>&1; then
    SYSCMD="systemctl --user"
else
    SYSCMD="systemctl"
fi

log()  { echo -e "${GREEN}[✓]${NC} $*"; }
warn() { echo -e "${YELLOW}[!]${NC} $*"; }
err()  { echo -e "${RED}[✗]${NC} $*"; }
info() { echo -e "${CYAN}[i]${NC} $*"; }

# Available models
declare -A MODELS
MODELS[e4b]="/home/darkseid/llama.cpp/ai-models/google_gemma-4-E4B-it-Q4_K_M.gguf|99|5GB|42 t/s|GPU completa"
MODELS[12b]="/home/darkseid/llama.cpp/ai-models/gemma-4-12b-it-Q4_K_M.gguf|40|6.7GB|16 t/s|GPU parcial"
MODELS[26b]="/home/darkseid/llama.cpp/ai-models/google_gemma-4-26B-A4B-it-Q4_K_M.gguf|0|17GB|1-3 t/s|CPU-only"
MODELS[26b0]="/home/darkseid/llama.cpp/ai-models/gemma-4-26B_q4_0-it.gguf|0|14.4GB|1-3 t/s|CPU-only"

get_current_model() {
    if [[ -f "$CONF_FILE" ]]; then
        local path
        path=$(grep "^MODEL_PATH=" "$CONF_FILE" | cut -d= -f2-)
        case "$path" in
            *E4B*) echo "e4b" ;;
            *12b*) echo "12b" ;;
            *26B-A4B-it*) echo "26b" ;;
            *26B_q4_0*) echo "26b0" ;;
            *) echo "unknown" ;;
        esac
    else
        echo "none"
    fi
}

do_start() {
    info "Iniciando Gemma 4 AI Server..."
    $SYSCMD start "$SERVICE" 2>/dev/null || true
    sleep 2
    if $SYSCMD is-active "$SERVICE" &>/dev/null; then
        log "Servidor iniciado"
        do_show_url
    else
        err "Error al iniciar. Verifica: $SYSCMD status $SERVICE"
        $SYSCMD status "$SERVICE" --no-pager 2>/dev/null || true
    fi
}

do_stop() {
    info "Deteniendo Gemma 4 AI Server..."
    $SYSCMD stop "$SERVICE" 2>/dev/null || true
    log "Servidor detenido"
}

do_restart() {
    info "Reiniciando Gemma 4 AI Server..."
    $SYSCMD restart "$SERVICE" 2>/dev/null || true
    sleep 3
    if $SYSCMD is-active "$SERVICE" &>/dev/null; then
        log "Servidor reiniciado"
        do_show_url
    else
        err "Error al reiniciar"
    fi
}

do_status() {
    echo -e "\n${BOLD}${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  Gemma 4 AI Server — Estado${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════${NC}\n"

    # Service status
    if $SYSCMD is-active "$SERVICE" &>/dev/null; then
        log "Servicio: Activo"
    else
        warn "Servicio: Inactivo"
    fi

    if $SYSCMD is-enabled "$SERVICE" &>/dev/null 2>&1; then
        log "Auto-start en boot: Habilitado"
    else
        warn "Auto-start en boot: Deshabilitado"
    fi

    # Current model
    local current
    current=$(get_current_model)
    if [[ "$current" != "none" && "$current" != "unknown" ]]; then
        IFS='|' read -r path ngl size speed gpu <<< "${MODELS[$current]}"
        echo ""
        info "Modelo actual: ${BOLD}$current${NC}"
        echo "  Archivo: $(basename "$path")"
        echo "  Tamaño: $size"
        echo "  Velocidad: $speed"
        echo "  GPU: $gpu (ngl=$ngl)"
    else
        warn "Modelo no configurado"
    fi

    # API check
    echo ""
    if curl -s http://localhost:9090/v1/models &>/dev/null; then
        log "API: http://localhost:9090 ✓"
        local model_list
        model_list=$(curl -s http://localhost:9090/v1/models 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); [print(f'  - {m[\"id\"]}') for m in d.get('data',[])]" 2>/dev/null || echo "  (no se pudo listar)")
        echo "$model_list"
    else
        warn "API: No responde en puerto 9090"
    fi
    echo ""
}

do_show_url() {
    local port
    port=$(grep "^PORT=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "9090")
    echo ""
    info "API OpenAI-compatible: http://localhost:${port}/v1"
    info "Web UI: http://localhost:${port}"
    echo ""
}

do_switch() {
    local model="${1:-}"
    if [[ -z "$model" ]]; then
        echo -e "\n${BOLD}Modelos disponibles:${NC}\n"
        for key in e4b 12b 26b 26b0; do
            IFS='|' read -r path ngl size speed gpu <<< "${MODELS[$key]}"
            local marker=""
            [[ "$(get_current_model)" == "$key" ]] && marker=" ${GREEN}(actual)${NC}"
            printf "  ${BOLD}%-6s${NC} %s — %s — %s${marker}\n" "$key" "$size" "$speed" "$gpu"
        done
        echo ""
        echo "Uso: $0 switch <modelo>"
        echo "Ejemplo: $0 switch e4b"
        return 0
    fi

    # Validate model
    if [[ -z "${MODELS[$model]+x}" ]]; then
        err "Modelo desconocido: $model"
        echo "Opciones: e4b, 12b, 26b, 26b0"
        return 1
    fi

    IFS='|' read -r path ngl size speed gpu <<< "${MODELS[$model]}"

    # Check file exists
    if [[ ! -f "$path" ]]; then
        err "Archivo no encontrado: $path"
        return 1
    fi

    # Write config
    cat > "$CONF_FILE" << EOF
# Gemma 4 Server Configuration
# Model: $model ($size, $speed)

MODEL_PATH=$path
NGL=$ngl
HOST=0.0.0.0
PORT=9090
CTX_SIZE=4096
EXTRA_ARGS=
EOF

    log "Configuración actualizada: $model ($size, $ngl GPU layers)"
    info "Reiniciando servicio..."
    do_restart
}

do_logs() {
    local lines="${1:-50}"
    $SYSCMD status "$SERVICE" --no-pager 2>/dev/null || true
    echo ""
    journalctl --user -u "$SERVICE" --no-pager -n "$lines" 2>/dev/null || \
    journalctl -u "$SERVICE" --no-pager -n "$lines" 2>/dev/null || \
    warn "No se pudieron obtener logs"
}

do_enable() {
    $SYSCMD enable "$SERVICE" 2>/dev/null || true
    log "Auto-start habilitado en boot"
}

do_disable() {
    $SYSCMD disable "$SERVICE" 2>/dev/null || true
    log "Auto-start deshabilitado"
}

do_swap() {
    local action="${1:-status}"
    
    case "$action" in
        on)
            info "Activando modo swap normal..."
            sed -i 's/^USE_SWAP=false/USE_SWAP=true/' "$CONF_FILE"
            sed -i 's/^SWAP_AGGRESSIVE=true/SWAP_AGGRESSIVE=false/' "$CONF_FILE"
            log "USE_SWAP=true, SWAP_AGGRESSIVE=false (CTX=32768)"
            info "Hibernación disponible (limitada)"
            info "Reiniciando servicio..."
            do_restart
            ;;
        off)
            info "Desactivando modo swap..."
            sed -i 's/^USE_SWAP=true/USE_SWAP=false/' "$CONF_FILE"
            log "USE_SWAP=false (CTX=16384)"
            info "Hibernación disponible completa"
            info "Reiniciando servicio..."
            do_restart
            ;;
        aggressive)
            info "Activando modo swap AGRESIVO..."
            sed -i 's/^USE_SWAP=false/USE_SWAP=true/' "$CONF_FILE"
            sed -i 's/^SWAP_AGGRESSIVE=false/SWAP_AGGRESSIVE=true/' "$CONF_FILE"
            log "USE_SWAP=true, SWAP_AGGRESSIVE=true (CTX=65536)"
            warn "⚠️ La hibernación NO estará disponible"
            info "Reiniciando servicio..."
            do_restart
            ;;
        status)
            echo -e "\n${BOLD}${CYAN}═══════════════════════════════════════════${NC}"
            echo -e "${BOLD}${CYAN}  Estado de Swap — Gemma 4 AI Server${NC}"
            echo -e "${BOLD}${CYAN}═══════════════════════════════════════════${NC}\n"
            
            # Read config
            local use_swap swap_aggressive ctx_normal ctx_swap ctx_aggressive
            use_swap=$(grep "^USE_SWAP=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "false")
            swap_aggressive=$(grep "^SWAP_AGGRESSIVE=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "false")
            ctx_normal=$(grep "^CTX_SIZE_NORMAL=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "16384")
            ctx_swap=$(grep "^CTX_SIZE_SWAP=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "32768")
            ctx_aggressive=$(grep "^CTX_SIZE_AGGRESSIVE=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "65536")
            
            # Current mode
            if [[ "$use_swap" == "true" && "$swap_aggressive" == "true" ]]; then
                log "Modo: ${BOLD}AGRESIVO${NC} (toda la swap)"
                info "CTX_SIZE efectivo: $ctx_aggressive (~28GB RAM+Swap)"
                warn "⚠️ La hibernación NO está disponible"
            elif [[ "$use_swap" == "true" ]]; then
                log "Modo: ${BOLD}NORMAL${NC} (swap con reserva)"
                info "CTX_SIZE efectivo: $ctx_swap (~14GB RAM+Swap)"
                info "Hibernación disponible (limitada)"
            else
                log "Modo: ${BOLD}SIN SWAP${NC}"
                info "CTX_SIZE efectivo: $ctx_normal (~7GB RAM)"
                log "✅ Hibernación disponible completa"
            fi
            
            # Memory usage
            echo ""
            info "Memoria del sistema:"
            free -h | head -2
            
            # VRAM
            echo ""
            info "VRAM GPU:"
            nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null || echo "  No disponible"
            
            # Server status
            echo ""
            if $SYSCMD is-active "$SERVICE" &>/dev/null; then
                log "Servicio: Activo"
                local port
                port=$(grep "^PORT=" "$CONF_FILE" 2>/dev/null | cut -d= -f2 || echo "9090")
                info "API: http://localhost:$port"
            else
                warn "Servicio: Inactivo"
            fi
            echo ""
            ;;
        *)
            echo "Uso: $0 swap <on|off|aggressive|status>"
            echo ""
            echo "  on          Modo swap normal (CTX=32768, hibernación limitada)"
            echo "  off         Sin swap (CTX=16384, hibernación completa)"
            echo "  aggressive  Modo agresivo (CTX=65536, sin hibernación)"
            echo "  status      Ver estado actual"
            ;;
    esac
}

# ── Main ──────────────────────────────────────────────────
ACTION="${1:-}"
case "$ACTION" in
    start)    do_start ;;
    stop)     do_stop ;;
    restart)  do_restart ;;
    status)   do_status ;;
    logs)     do_logs "${2:-50}" ;;
    switch)   do_switch "${2:-}" ;;
    list)     do_switch "" ;;
    enable)   do_enable ;;
    disable)  do_disable ;;
    swap)     do_swap "${2:-status}" ;;
    url)      do_show_url ;;
    *)
        echo -e "${BOLD}gemma4-ctl${NC} — Controla el servicio Gemma 4 AI Server\n"
        echo "Uso: $0 <comando> [argumentos]"
        echo ""
        echo "Comandos:"
        echo "  start           Iniciar el servidor"
        echo "  stop            Detener el servidor"
        echo "  restart         Reiniciar el servidor"
        echo "  status          Ver estado completo"
        echo "  logs [n]        Ver últimos n logs (default: 50)"
        echo "  switch <modelo> Cambiar de modelo"
        echo "  list            Ver modelos disponibles"
        echo "  enable          Habilitar auto-start en boot"
        echo "  disable         Deshabilitar auto-start"
        echo "  swap <on|off|aggressive> Modo swap"
        echo "  url             Mostrar URLs de acceso"
        echo ""
        echo "Modelos: e4b, 12b, 26b, 26b0"
        echo ""
        echo "Ejemplos:"
        echo "  $0 status                    # Ver estado"
        echo "  $0 switch e4b                # Cambiar a E4B (rápido)"
        echo "  $0 switch 12b                # Cambiar a 12B (calidad)"
        echo "  $0 swap on                   # Activar modo swap normal"
        echo "  $0 swap off                  # Desactivar swap"
        echo "  $0 swap aggressive           # Modo agresivo (sin hibernación)"
        echo "  $0 start                     # Iniciar servidor"
        echo "  $0 logs 100                  # Ver últimos 100 logs"
        ;;
esac
