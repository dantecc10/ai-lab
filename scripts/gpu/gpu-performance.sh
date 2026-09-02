#!/bin/bash
# gpu-performance.sh — Activa/desactiva modo máximo rendimiento para la GPU
# Uso: ./gpu-performance.sh [--on|--off|--boot|--status]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

GPU_ADDR="0000:01:00.0"
# shellcheck disable=SC2034
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

log()   { echo -e "${GREEN}[✓]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
err()   { echo -e "${RED}[✗]${NC} $*"; }
info()  { echo -e "${CYAN}[i]${NC} $*"; }

wake_gpu() {
    info "Despertando GPU del D3cold..."
    local power_state
    power_state=$(cat /sys/bus/pci/devices/${GPU_ADDR}/power_state 2>/dev/null || echo "unknown")

    if [[ "$power_state" == "D3cold" || "$power_state" == "D3hot" ]]; then
        # Method 1: Remove and rescan PCI device
        if echo 0 > /sys/bus/pci/devices/${GPU_ADDR}/remove 2>/dev/null; then
            log "Dispositivo PCI removido"
            sleep 1
            echo 1 > /sys/bus/pci/rescan 2>/dev/null
            log "Re-escaneo PCI completado"
            sleep 3
        else
            warn "No se pudo remover por sysfs, intentando con setpci..."
            # Method 2: Try to wake via power state
            echo "on" > /sys/bus/pci/devices/${GPU_ADDR}/power/control 2>/dev/null || true
            sleep 2
        fi
    else
        log "GPU ya está activa (power_state: $power_state)"
    fi

    # Verify
    power_state=$(cat /sys/bus/pci/devices/${GPU_ADDR}/power_state 2>/dev/null || echo "unknown")
    if [[ "$power_state" == "D0" ]]; then
        log "GPU despertada exitosamente (D0)"
        return 0
    else
        warn "GPU power_state: $power_state (se intentará continuar de todos modos)"
        return 0
    fi
}

disable_d3cold() {
    info "Deshabilitando D3cold..."
    local d3cold_file="/sys/bus/pci/devices/${GPU_ADDR}/power/d3cold_allowed"
    if [[ -f "$d3cold_file" ]]; then
        echo 0 > "$d3cold_file" 2>/dev/null
        log "D3cold deshabilitado"
    else
        warn "Archivo d3cold_allowed no encontrado — se aplicará via modprobe en next boot"
    fi
}

enable_persistence() {
    info "Activando persistence mode..."
    if timeout 10 nvidia-smi -pm 1 &>/dev/null; then
        log "Persistence mode activado"
    else
        err "No se pudo activar persistence mode (¿nvidia-smi no responde?)"
        return 1
    fi
}

set_max_power_limit() {
    info "Verificando power limit..."
    local max_limit current_limit
    max_limit=$(timeout 10 nvidia-smi --query-gpu=power.max_limit --format=csv,noheader 2>/dev/null | tr -d ' W' || echo "")
    current_limit=$(timeout 10 nvidia-smi --query-gpu=power.limit --format=csv,noheader 2>/dev/null | tr -d ' []W' || echo "")

    if [[ -z "$max_limit" || "$max_limit" == *"N/A"* ]]; then
        info "Power limit no expuesto por VBIOS (normal en laptops) — usando límite del fabricante"
        return 0
    fi

    if [[ "$max_limit" == "$current_limit" || -z "$current_limit" || "$current_limit" == *"N/A"* ]]; then
        info "Power limit ya está en el máximo o no es configurable (${max_limit}W reportado)"
        return 0
    fi

    if timeout 10 nvidia-smi -pl "$max_limit" &>/dev/null; then
        log "Power limit establecido a ${max_limit}W (máximo)"
    else
        info "Power limit no configurable por software (bloqueado por VBIOS del fabricante) — usando valor por defecto"
    fi
}

force_performance_mode() {
    info "Forzando modo performance..."
    # Disable runtime PM
    echo "on" > /sys/bus/pci/devices/${GPU_ADDR}/power/control 2>/dev/null
    log "Runtime PM deshabilitado (power/control = on)"

    # Check if nvidia-powerd is causing issues
    if systemctl is-active nvidia-powerd &>/dev/null; then
        warn "nvidia-powerd está activo — puede conflictuar con modo máximo rendimiento"
        info "Considera deshabilitarlo: sudo systemctl disable --now nvidia-powerd"
    fi
}

show_status() {
    echo -e "\n${BOLD}${CYAN}── Estado de Performance GPU ──${NC}\n"
    local pstate pci_power persist
    pci_power=$(cat /sys/bus/pci/devices/${GPU_ADDR}/power_state 2>/dev/null || echo "N/A")
    pstate=$(timeout 5 nvidia-smi --query-gpu=pstate --format=csv,noheader 2>/dev/null || echo "N/A")
    persist=$(pgrep -f nvidia-persistenced &>/dev/null && echo "running" || echo "stopped")

    printf "  %-30s %s\n" "PCI Power State:" "$pci_power"
    printf "  %-30s %s\n" "Performance State:" "$pstate"
    printf "  %-30s %s\n" "Persistenced:" "$persist"

    local d3cold
    d3cold=$(cat /sys/bus/pci/devices/${GPU_ADDR}/power/d3cold_allowed 2>/dev/null || echo "N/A")
    printf "  %-30s %s\n" "D3cold Allowed:" "$d3cold"
    echo ""
}

enable_all() {
    echo -e "\n${BOLD}${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  GPU Maximum Performance — Setup${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════${NC}\n"

    wake_gpu
    disable_d3cold
    force_performance_mode
    enable_persistence
    set_max_power_limit

    echo -e "\n${GREEN}${BOLD}✅ Configuración de máximo rendimiento activada${NC}\n"
    show_status
}

disable_all() {
    echo -e "\n${BOLD}${YELLOW}═══════════════════════════════════════════${NC}"
    echo -e "${BOLD}${YELLOW}  GPU — Restaurando modo ahorro de energía${NC}"
    echo -e "${BOLD}${YELLOW}═══════════════════════════════════════════${NC}\n"

    info "Desactivando persistence mode..."
    timeout 10 nvidia-smi -pm 0 &>/dev/null && log "Persistence mode desactivado" || warn "No se pudo"

    info "Restaurando power limit por defecto..."
    local def_limit
    def_limit=$(timeout 10 nvidia-smi --query-gpu=power.default_limit --format=csv,noheader 2>/dev/null | tr -d ' W' || echo "")
    if [[ -n "$def_limit" ]]; then
        timeout 10 nvidia-smi -pl "$def_limit" &>/dev/null && log "Power limit restaurado a ${def_limit}W" || warn "No se pudo"
    fi

    info "Habilitando runtime PM..."
    echo "auto" > /sys/bus/pci/devices/${GPU_ADDR}/power/control 2>/dev/null
    log "Runtime PM habilitado (power/control = auto)"

    echo -e "\n${YELLOW}✅ Modo ahorro de energía restaurado${NC}\n"
    show_status
}

# ── Main ──────────────────────────────────────────────────
MODE="${1:-}"
case "$MODE" in
    --on)       enable_all ;;
    --off)      disable_all ;;
    --boot)
        # Silent mode for systemd service — only does essential setup
        wake_gpu &>/dev/null
        disable_d3cold &>/dev/null
        force_performance_mode &>/dev/null
        enable_persistence &>/dev/null || true
        set_max_power_limit &>/dev/null || true
        ;;
    --status)   show_status ;;
    *)
        echo -e "${BOLD}gpu-performance.sh${NC} — Control de rendimiento GPU NVIDIA\n"
        echo "Uso: $0 [opción]"
        echo ""
        echo "Opciones:"
        echo "  --on      Activar máximo rendimiento (wake + persistence + max power)"
        echo "  --off     Restaurar modo ahorro de energía"
        echo "  --boot    Configuración silenciosa para arranque (systemd)"
        echo "  --status  Mostrar estado actual"
        echo ""
        echo "Sin argumentos: modo interactivo"
        echo ""
        read -p "¿Activar máximo rendimiento? [S/n]: " answer
        if [[ "${answer,,}" != "n" ]]; then
            enable_all
        else
            disable_all
        fi
        ;;
esac
