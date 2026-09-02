# AI Lab — Roadmap y Fases de Evolución

Plan de evolución técnica para dotar al ecosistema **AI Lab** de máxima capacidad de ejecución autónoma, control granular de seguridad, automatización basada en eventos y memoria contextual de largo plazo.

---

## Resumen Ejecutivo del Roadmap

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│ FASE 1: Motor de Ejecución Autónoma, Guardrails & Bucle ReAct [COMPLETADO]       │
│ • Human-in-the-Loop Guardrails (Safe/Medium/High Risk Policies)                  │
│ • Bucle ReAct con Auto-Corrección y Reflexión de Errores                        │
│ • Sistema de Auditoría y Tracing Local (SQLite / Métricas de Latencia y GPU)     │
│ • Sandboxing y Ejecución Segura de Scripts / Comandos                            │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ FASE 2: Motor de Automatización por Eventos y Tareas Programadas [COMPLETADO]   │
│ • Event Bus Reactivo (Inotify Watcher, Hardware Health Monitor, Alert DB)        │
│ • Motor de Flujos Declarativos (DAG Pipelines en JSON/YAML)                      │
│ • Tools MCP: workflow_run, workflow_list, workflow_status (151 tools)           │
│ • Servicio systemd: event-hub.service                                            │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ FASE 3: Memoria Vectorial Semántica & RAG Local [COMPLETADO]                     │
│ • Base de Datos Vectorial Local (~/.local/share/ai-lab/vectors/vector_store.db)   │
│ • Embeddings Densos L2 en CPU (0% VRAM GPU) con Filtrado de Stop Words           │
│ • Indexador Automático de Documentación, Repositorios y Notas con Chunking       │
│ • Tools MCP: vector_search, vector_index_path, vector_remember, vector_stats     │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ FASE 4: Navegación Web Headless & Sincronización de Identidades [COMPLETADO]     │
│ • Brave Browser Headless Driver con Chrome DevTools Protocol (CDP nativo :9222)   │
│ • Sincronizador de Identidades/Cookies desde Brave (~/.config/BraveSoftware)     │
│ • Tools MCP: browser_navigate, browser_click, browser_type, browser_screenshot   │
│ • Tools MCP: browser_extract_text, browser_sync_brave_profile, browser_status    │
└────────────────────────────────────────┬─────────────────────────────────────────┘
                                         │
                                         ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│ FASE 5: Voz Bidireccional Full-Duplex & Visión Multimodal [COMPLETADO]            │
│ • Motor de Voz Full-Duplex con Soporte Barge-In (Interrupción Inmediata de Audio) │
│ • Voice Activity Detection (VAD) inteligente con auto-corte de silencio           │
│ • Motor de Visión Multimodal Local (Gemma 4 / llama.cpp) e integración Tesseract │
│ • Tools MCP: voice_speak, voice_listen, voice_status, vision_analyze_image, etc. │
└──────────────────────────────────────────────────────────────────────────────────┘
```

---

## Detalle de Fases y Entregables

### 🚀 Fase 1: Motor de Ejecución Autónoma, Guardrails & Bucle ReAct *(En Curso)*
- **Objetivo**: Dotar a la IA de capacidad para resolver tareas complejas de múltiples pasos de forma autónoma con supervisión de seguridad y métricas de ejecución.
- **Entregables**:
  1. `configs/security-policies.conf`: Definición de niveles de criticidad de herramientas (`safe`, `medium`, `high_risk`, `blocked`).
  2. Middleware de Intercepción y Confirmación de Seguridad: Validación previa antes de ejecutar acciones de nivel Rojo (`system_shutdown`, `process_kill`, `rm`, `git_push --force`, etc.).
  3. Bucle de Reflexión y Auto-Corrección (`scripts/mcp_assistant.py`): Si una herramienta o comando falla con `exit code != 0`, la IA analiza el error, propone una corrección y reintenta de forma iterativa hasta alcanzar el objetivo.
  4. Módulo de Auditoría y Traces (`scripts/tools/audit_logger.py` y `~/.local/share/ai-lab/audit_traces.db`): Registro de tiempos de respuesta, tokens consumidos, uso de GPU y estado de cada llamada.
  5. Herramientas MCP de Auditoría: `audit_get_metrics`, `audit_list_traces`.

---

### ⚡ Fase 2: Automatización por Eventos y Flujos DAG
- **Objetivo**: Convertir a AI Lab en un agente proactivo que reacciona a eventos del entorno sin requerir un prompt manual continuo.
- **Entregables**:
  1. `scripts/automation/event_hub.py`: Demonio de eventos reactivos:
     - `Inotify File Watcher`: Monitoreo de `~/Downloads` y carpetas de proyecto para auto-procesar archivos.
     - `Hardware Watcher`: Monitor de alertas de temperatura de GPU (>80°C), memoria swap crítica o desconexión de red.
     - `Webhook Listener`: Recepción de eventos en puerto 9095 (GitHub webhooks, alertas de servidores externos).
  2. Motor de Flujos Declarativos (`scripts/automation/dag_runner.py`): Ejecución de secuencias YAML tipo cron avanzado (ej. resumen matutino, auditoría de seguridad nocturna, respaldos).

---

### 🧠 Fase 3: Memoria Vectorial Semántica & RAG Local
- **Objetivo**: Proveer memoria asociativa a largo plazo sobre todo el código, documentación y notas del usuario sin desbordar el contexto del modelo.
- **Entregables**:
  1. Base de datos vectorial local basada en LanceDB / SQLite-vss con modelo de embeddings `bge-small` o `all-MiniLM-L6-v2` corriendo en CPU con aceleración ONNX.
  2. Indexador en segundo plano de repositorios, documentación (`~/ai-lab`, `~/.notes`, etc.).
  3. Herramientas MCP: `vector_search`, `vector_index_path`, `vector_query_docs`.
  4. Extracción automática de preferencias de usuario y hechos persistentes.

---

### 🌐 Fase 4: Navegación Web Headless (Playwright)
- **Objetivo**: Automatizar flujos web complejos que requieren JavaScript dinámico, login y clics interactivos.
- **Entregables**:
  1. Servidor MCP `browser_mcp_server.py` basado en Playwright.
  2. Herramientas: `browser_navigate`, `browser_click`, `browser_type`, `browser_screenshot`, `browser_extract_table`, `browser_fill_form`.

---

### 🎙️ Fase 5: Voz Full-Duplex & Visión Multimodal
- **Objetivo**: Conversación por voz bidireccional natural y capacidad de ver la pantalla del usuario.
- **Entregables**:
  1. Detección de actividad vocal (Silero VAD) en `scripts/voice/voice_hub.py` para permitir interrumpir a la IA mientras responde (Barge-In).
  2. Streaming continuo de tokens a Piper TTS.
  3. Soporte para modelos de visión locales en GPU/CPU para analizar capturas de pantalla de `system_screenshot`.
