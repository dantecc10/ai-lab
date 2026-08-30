# Changelog

Historial de cambios y mejoras del sistema AI Lab.

## [1.0.0] - 2026-08-29

### Added
- Sistema base con GPU NVIDIA RTX 5060 Laptop (8GB VRAM)
- llama.cpp v0.3.0-dev (build b10688)
- Modelos Gemma 4: 12B, E4B, 26B
- Servidor principal (puerto 9090) con 12B en GPU
- Sub-agente E4B (puerto 9091) en CPU
- Open WebUI (puerto 9092)
- Whisper STT (puerto 9093)
- 39 tools MCP:
  - Smart Home (Kasa): 2 tools
  - Sistema: 15 tools
  - Navegador: 3 tools
  - Multimedia: 2 tools
  - Spotify: 10 tools
  - Memoria: 5 tools
  - Delegación: 1 tool
- Sistema de memoria persistente con SQLite
- Notas rápidas en ~/.notes/
- System prompt con keywords de delegación
- Modo swap (3 modos: off/on/aggressive)
- Servicios systemd para todos los componentes

### Fixed
- GPU D3cold: Deshabilitado para máximo rendimiento
- S0ix: Deshabilitado en system76-power.conf
- CUDA OOM: Reducido NGL de 40 a 30 para CTX=32768
- MCP server: Corregido Python path para duckduckgo-search

### Changed
- Web search: Cambiado de Brave browser a DuckDuckGo API
- System prompt: Agregadas keywords para delegación ("tú mismo", "no delegues")
- Documentación: README completo actualizado

## [0.9.0] - 2026-08-28

### Added
- Sistema de voz con wake word ("Hey Jarvis", "Alexa")
- Push-to-Talk con atajo de teclado (F5)
- Piper TTS para respuestas de voz
- Control domótico de enchufes Kasa
- Scripts de GPU: status, performance, monitor, reset, cuda-test

### Fixed
- Power limit: VBIOS bloqueado por ASUS (55W default)
- Persistence mode: Activado para estabilidad

## [0.8.0] - 2026-08-27

### Added
- Instalación de llama.cpp desde fuente
- Descarga de modelos Gemma 4 GGUF
- Configuración inicial de GPU
- Script de setup (gpu-setup.sh)

### Fixed
- Driver NVIDIA: Actualizado a 580.173.02
- CUDA: Instalado CUDA 12.0

## [0.7.0] - 2026-08-26

### Added
- Hardware diagnosticado:
  - GPU: NVIDIA RTX 5060 Laptop
  - RAM: 16GB
  - SO: Pop!_OS 24.04 LTS
- Instalación de dependencias base
