#!/bin/bash
# gpu-status.sh — Muestra estado completo de la GPU NVIDIA
# Uso: ./gpu-status.sh [--json]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

GPU_ADDR="0000:01:00.0"
JSON_MODE=false

if [[ "${1:-}" == "--json" ]]; then
    JSON_MODE=true
fi

header() {
    echo -e "\n${BOLD}${CYAN}═══════════════════════════════════════════${NC}"
    echo -e "${BOLD}${CYAN}  $1${NC}"
    echo -e "${BOLD}${CYAN}═══════════════════════════════════════════${NC}"
}

check_nvidia_smi() {
    if ! timeout 5 nvidia-smi &>/dev/null; then
        echo -e "${RED}[!] nvidia-smi no responde — la GPU puede estar en D3cold o el driver falló${NC}"
        return 1
    fi
    return 0
}

print_section() {
    local label="$1"
    local value="$2"
    local color="${3:-$NC}"
    echo -e "  ${BOLD}$(printf '%-25s' "$label")${NC} ${color}${value}${NC}"
}

# ── PCI / Hardware ──────────────────────────────────────
header "GPU Hardware"
PCI_CLASS=$(lspci -n -s "${GPU_ADDR}" 2>/dev/null | awk '{print $2}' || echo "N/A")
PCI_DESC=$(lspci -s "${GPU_ADDR}" 2>/dev/null | cut -d: -f3- | sed 's/^ //' || echo "N/A")
print_section "Dispositivo" "$PCI_DESC"
print_section "Dirección PCI" "$GPU_ADDR"
print_section "Clase PCI" "$PCI_CLASS"

DRIVER=$(cat /sys/bus/pci/devices/${GPU_ADDR}/driver/module/module/drivers/nvidia/nvidia/version 2>/dev/null || \
         cat /proc/driver/nvidia/version 2>/dev/null | head -1 | awk -F': ' '{print $2}' || echo "N/A")
print_section "Driver" "$DRIVER"

# ── Power State ─────────────────────────────────────────
header "Power State"
PCI_POWER=$(cat /sys/bus/pci/devices/${GPU_ADDR}/power_state 2>/dev/null || echo "N/A")
RUNTIME_STATUS=$(cat /sys/bus/pci/devices/${GPU_ADDR}/power/runtime_status 2>/dev/null || echo "N/A")
POWER_CONTROL=$(cat /sys/bus/pci/devices/${GPU_ADDR}/power/control 2>/dev/null || echo "N/A")
D3COLD_ALLOWED=$(cat /sys/bus/pci/devices/${GPU_ADDR}/power/d3cold_allowed 2>/dev/null || echo "N/A (no disponible)")

if [[ "$PCI_POWER" == "D3cold" ]]; then
    print_section "PCI Power State" "$PCI_POWER" "$RED"
elif [[ "$PCI_POWER" == "D0" ]]; then
    print_section "PCI Power State" "$PCI_POWER" "$GREEN"
else
    print_section "PCI Power State" "$PCI_POWER" "$YELLOW"
fi
print_section "Runtime Status" "$RUNTIME_STATUS"
print_section "Power Control" "$POWER_CONTROL"
print_section "D3cold Allowed" "$D3COLD_ALLOWED"

# ── Persistenced ────────────────────────────────────────
header "Persistence Mode"
PERSIST_PID=$(pgrep -f nvidia-persistenced 2>/dev/null || echo "")
if [[ -n "$PERSIST_PID" ]]; then
    PERSIST_ARGS=$(cat /proc/$PERSIST_PID/cmdline 2>/dev/null | tr '\0' ' ' || echo "N/A")
    if echo "$PERSIST_ARGS" | grep -q "persistence-mode"; then
        print_section "Persistenced" "${GREEN}Activo (persistence-mode)${NC}"
    else
        print_section "Persistenced" "${YELLOW}Activo pero SIN persistence-mode${NC}"
    fi
else
    print_section "Persistenced" "${RED}No está corriendo${NC}"
fi

# ── nvidia-smi info ─────────────────────────────────────
if check_nvidia_smi; then
    header "nvidia-smi"
    SMIPROD=$(nvidia-smi --query-gpu=name,driver_version,pci.bus_id,power.limit,power.default_limit,power.max_limit --format=csv,noheader 2>/dev/null || echo "N/A")
    if [[ -n "$SMIPROD" && "$SMIPROD" != "N/A" ]]; then
        IFS=',' read -r GPU_NAME GPU_DRV GPU_BUS GPU_PLIMIT GPU_PDEF GPU_PMAX <<< "$SMIPROD"
        GPU_NAME=$(echo "$GPU_NAME" | xargs)
        GPU_DRV=$(echo "$GPU_DRV" | xargs)
        GPU_BUS=$(echo "$GPU_BUS" | xargs)
        GPU_PLIMIT=$(echo "$GPU_PLIMIT" | tr -d '[]' | xargs)
        GPU_PDEF=$(echo "$GPU_PDEF" | tr -d '[]' | xargs)
        GPU_PMAX=$(echo "$GPU_PMAX" | tr -d '[]' | xargs)
        print_section "Modelo" "$GPU_NAME"
        print_section "Driver" "$GPU_DRV"
        print_section "Bus ID" "$GPU_BUS"
        if [[ "$GPU_PLIMIT" == *"N/A"* ]]; then
            print_section "Power Limit" "No configurable (VBIOS fabricante)"
        else
            print_section "Power Limit" "${GPU_PLIMIT}"
        fi
        print_section "Power Default" "${GPU_PDEF}"
        print_section "Power Max" "${GPU_PMAX}"
    fi

    header "GPU Metrics"
    TEMP=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader 2>/dev/null || echo "N/A")
    UTIL=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader 2>/dev/null || echo "N/A")
    MEM_UTIL=$(nvidia-smi --query-gpu=utilization.memory --format=csv,noheader 2>/dev/null || echo "N/A")
    MEM_USED=$(nvidia-smi --query-gpu=memory.used --format=csv,noheader 2>/dev/null || echo "N/A")
    MEM_TOTAL=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader 2>/dev/null || echo "N/A")
    MEM_PERCENT=$(nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null | awk -F', ' '{printf "%.1f%%", $1/$2*100}' || echo "N/A")
    CLOCKS_SM=$(nvidia-smi --query-gpu=clocks.current.graphics --format=csv,noheader 2>/dev/null || echo "N/A")
    CLOCKS_MEM=$(nvidia-smi --query-gpu=clocks.current.memory --format=csv,noheader 2>/dev/null || echo "N/A")
    CLOCKS_VID=$(nvidia-smi --query-gpu=clocks.current.video --format=csv,noheader 2>/dev/null || echo "N/A")
    PWR_DRAW=$(nvidia-smi --query-gpu=power.draw --format=csv,noheader 2>/dev/null || echo "N/A")
    PSTATE=$(nvidia-smi --query-gpu=pstate --format=csv,noheader 2>/dev/null || echo "N/A")

    if [[ "$TEMP" != "N/A" ]] && (( TEMP >= 80 )); then
        TEMP_COLOR="$RED"
    elif [[ "$TEMP" != "N/A" ]] && (( TEMP >= 65 )); then
        TEMP_COLOR="$YELLOW"
    else
        TEMP_COLOR="$GREEN"
    fi

    print_section "Temperatura" "${TEMP}°C" "$TEMP_COLOR"
    print_section "Uso GPU" "$UTIL"
    print_section "Uso VRAM" "$MEM_UTIL"
    print_section "VRAM" "${MEM_USED} / ${MEM_TOTAL} (${MEM_PERCENT})"
    print_section "Clock SM" "$CLOCKS_SM"
    print_section "Clock Memoria" "$CLOCKS_MEM"
    print_section "Clock Video" "$CLOCKS_VID"
    print_section "Potencia" "$PWR_DRAW"
    print_section "Performance State" "$PSTATE"

    # ── Processes ────────────────────────────────────────
    header "Procesos GPU"
    PROCS=$(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader 2>/dev/null || echo "")
    if [[ -n "$PROCS" ]]; then
        echo "$PROCS" | while IFS=',' read -r pid pname pmem; do
            printf "  PID %-8s %-30s %s\n" "$pid" "$pname" "$pmem"
        done
    else
        echo -e "  ${YELLOW}(ningún proceso CUDA activo)${NC}"
    fi

    # ── CUDA check ──────────────────────────────────────
    header "CUDA"
    if command -v nvcc &>/dev/null; then
        CUDA_VER=$(nvcc --version 2>/dev/null | grep -oP 'release \K[0-9.]+' || echo "N/A")
        print_section "nvcc" "$CUDA_VER"
    else
        print_section "nvcc" "${YELLOW}No instalado (solo runtime disponible)${NC}"
    fi
    if [[ -f /usr/local/cuda/version.txt ]]; then
        print_section "CUDA Runtime" "$(cat /usr/local/cuda/version.txt)"
    fi
else
    header "nvidia-smi"
    echo -e "  ${RED}No disponible — la GPU está en D3cold o el driver falló${NC}"
    echo -e "  ${YELLOW}Intenta ejecutar: gpu-performance.sh para activar la GPU${NC}"
fi

echo ""
