#!/bin/bash
# gpu-monitor.sh — Monitoreo continuo de la GPU NVIDIA
# Uso: ./gpu-monitor.sh [--interval <seconds>] [--log <archivo>]

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

INTERVAL=2
LOG_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --interval|-i) INTERVAL="$2"; shift 2 ;;
        --log|-l) LOG_FILE="$2"; shift 2 ;;
        --help|-h)
            echo "gpu-monitor.sh — Monitoreo continuo de GPU"
            echo ""
            echo "Uso: $0 [opciones]"
            echo "  --interval, -i <s>   Intervalo en segundos (default: 2)"
            echo "  --log, -l <archivo>  Guardar logs a archivo"
            echo "  Ctrl+C para salir"
            exit 0 ;;
        *) shift ;;
    esac
done

if ! timeout 3 nvidia-smi &>/dev/null; then
    echo -e "${RED}Error: nvidia-smi no responde. La GPU puede estar en D3cold.${NC}"
    echo -e "${YELLOW}Ejecuta: gpu-performance.sh --on${NC}"
    exit 1
fi

clear
echo -e "${BOLD}${CYAN}GPU Monitor — Ctrl+C para salir${NC}"
echo -e "${CYAN}Intervalo: ${INTERVAL}s${NC}"
[[ -n "$LOG_FILE" ]] && echo -e "${CYAN}Log: ${LOG_FILE}${NC}"
echo ""

if [[ -n "$LOG_FILE" ]]; then
    echo "timestamp,temp_c,gpu_util%,mem_util%,mem_used_mb,mem_total_mb,power_w,clock_sm_mhz,clock_mem_mhz,pstate" > "$LOG_FILE"
fi

while true; do
    TS=$(date '+%H:%M:%S')

    read -r TEMP GPU_UTIL MEM_UTIL MEM_USED MEM_TOTAL PWR CLOCK_SM CLOCK_MEM PSTATE \
        < <(nvidia-smi --query-gpu=\
temperature.gpu,\
utilization.gpu,\
utilization.memory,\
memory.used,\
memory.total,\
power.draw,\
clocks.current.graphics,\
clocks.current.memory,\
pstate \
--format=csv,noheader,nounits 2>/dev/null || echo "N/A N/A N/A N/A N/A N/A N/A N/A N/A")

    if [[ "$TEMP" == "N/A" ]]; then
        echo -e "${RED}[${TS}] GPU no disponible${NC}"
        sleep "$INTERVAL"
        continue
    fi

    # Color for temperature
    TEMP_COLOR="$GREEN"
    (( TEMP >= 75 )) && TEMP_COLOR="$YELLOW"
    (( TEMP >= 90 )) && TEMP_COLOR="$RED"

    # Color for utilization
    UTIL_COLOR="$GREEN"
    (( GPU_UTIL >= 80 )) && UTIL_COLOR="$YELLOW"
    (( GPU_UTIL >= 95 )) && UTIL_COLOR="$RED"

    # Bar for memory
    MEM_PCT=0
    if [[ "$MEM_TOTAL" != "N/A" && "$MEM_TOTAL" -gt 0 ]] 2>/dev/null; then
        MEM_PCT=$(( MEM_USED * 100 / MEM_TOTAL ))
    fi
    BAR_LEN=20
    BAR_FILLED=$(( MEM_PCT * BAR_LEN / 100 ))
    BAR_EMPTY=$(( BAR_LEN - BAR_FILLED ))
    BAR=$(printf '%0.s█' $(seq 1 $BAR_FILLED 2>/dev/null) 2>/dev/null || true)
    BAR+=$(printf '%0.s░' $(seq 1 $BAR_EMPTY 2>/dev/null) 2>/dev/null || true)

    # Clear line and print
    printf "\r\033[K"
    printf "  ${BOLD}%s${NC} │ " "$TS"
    printf "${TEMP_COLOR}%3s°C${NC} │ " "$TEMP"
    printf "${UTIL_COLOR}%3s%%${NC} GPU │ " "$GPU_UTIL"
    printf " %3s%% MEM │ " "$MEM_UTIL"
    printf "${CYAN}%s${NC} ${MEM_PCT}%% │ " "$BAR"
    printf "%5sW │ " "$PWR"
    printf "SM:%s │ " "$CLOCK_SM"
    printf "MEM:%s │ " "$CLOCK_MEM"
    printf "%s" "$PSTATE"

    if [[ -n "$LOG_FILE" ]]; then
        echo "${TS},${TEMP},${GPU_UTIL},${MEM_UTIL},${MEM_USED},${MEM_TOTAL},${PWR},${CLOCK_SM},${CLOCK_MEM},${PSTATE}" >> "$LOG_FILE"
    fi

    sleep "$INTERVAL"
done
