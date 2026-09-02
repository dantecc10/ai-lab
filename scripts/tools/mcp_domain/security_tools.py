"""Security audit, secret detection, and log analysis tools"""

import os
import subprocess
from mcp_common.paths import HOME, safe_path
from mcp_common.logging import log_operation

TOOLS = [
    {
        "name": "security_audit",
        "description": "Auditoría básica de seguridad: permisos, puertos abiertos, usuarios.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "scope": {
                    "type": "string",
                    "enum": ["full", "ports", "files", "users"],
                    "description": "Alcance de la auditoría.",
                    "default": "full"
                }
            }
        }
    },
    {
        "name": "secret_detection",
        "description": "Detecta posibles secretos/claves en archivos de código.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Directorio a escanear."
                },
                "extensions": {
                    "type": "string",
                    "description": "Extensiones a escanear (ej: '.py,.js,.env').",
                    "default": ".py,.js,.ts,.env,.json,.yaml,.yml,.cfg,.conf"
                }
            }
        }
    },
    {
        "name": "log_analysis",
        "description": "Analiza logs del sistema: errores, warnings, patrones.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "log_file": {
                    "type": "string",
                    "description": "Ruta del archivo de log."
                },
                "lines": {
                    "type": "integer",
                    "description": "Últimas N líneas a analizar.",
                    "default": 100
                },
                "filter": {
                    "type": "string",
                    "description": "Filtrar por nivel (ERROR, WARN, INFO)."
                }
            },
            "required": ["log_file"]
        }
    },
    {
        "name": "audit_get_metrics",
        "description": "Consulta métricas agregadas de rendimiento de herramientas, tasa de éxito, latencia y uso de GPU/VRAM en las últimas N horas.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "hours": {
                    "type": "integer",
                    "description": "Número de horas hacia atrás para calcular métricas (default: 24)."
                }
            }
        }
    },
    {
        "name": "audit_list_traces",
        "description": "Lista las trazas de auditoría de ejecución de herramientas recientes para trazabilidad, depuración y auto-diagnóstico.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de trazas a recuperar (default: 10)."
                },
                "errors_only": {
                    "type": "boolean",
                    "description": "Si es true, solo devuelve trazas de herramientas que fallaron (default: false)."
                }
            }
        }
    },
]

# ── Handlers ───────────────────────────────────────────────
def _security_audit_handler(scope: str = "full") -> str:
    """Basic security audit."""
    try:
        output = "🔒 Auditoría de Seguridad\n\n"
        
        if scope in ["full", "ports"]:
            output += "📡 Puertos abiertos:\n"
            result = subprocess.run(
                ["ss", "-tlnp"],
                capture_output=True, text=True, timeout=10
            )
            lines = result.stdout.strip().split('\n')[1:]
            for line in lines[:20]:
                parts = line.split()
                if len(parts) >= 4:
                    output += f"  • {parts[3]} ({parts[5] if len(parts) > 5 else 'N/A'})\n"
            output += "\n"
        
        if scope in ["full", "users"]:
            output += "👤 Usuarios con login:\n"
            result = subprocess.run(
                ["grep", "-v", "nologin", "/etc/passwd"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.strip().split('\n')[:5]:
                parts = line.split(':')
                output += f"  • {parts[0]} (uid:{parts[2]})\n"
            output += "\n"
        
        if scope in ["full", "files"]:
            output += "📁 Archivos con permisos 777:\n"
            result = subprocess.run(
                ["find", HOME, "-perm", "777", "-type", "f", "-maxdepth", "3"],
                capture_output=True, text=True, timeout=10
            )
            files = result.stdout.strip().split('\n') if result.stdout.strip() else []
            for f in files[:10]:
                output += f"  ⚠️ {f}\n"
            if not files or files == ['']:
                output += "  ✅ Ninguno encontrado\n"
            output += "\n"
        
        return output
    
    except Exception as e:
        return f"Error en auditoría: {e}"



def _secret_detection_handler(path: str = None, extensions: str = ".py,.js,.ts,.env,.json,.yaml,.yml,.cfg,.conf") -> str:
    """Detect potential secrets in code."""
    try:
        if not path:
            path = HOME
        path = os.path.expanduser(path)
        
        # Common secret patterns
        secret_patterns = [
            r'(?i)(password|passwd|pwd)\s*[=:]\s*["\'][^"\']+["\']',
            r'(?i)(secret|token|api_key|apikey|api-key)\s*[=:]\s*["\'][^"\']+["\']',
            r'(?i)(access_key|secret_key)\s*[=:]\s*["\'][^"\']+["\']',
            r'(?i)(AWS_ACCESS_KEY_ID|AWS_SECRET_ACCESS_KEY)\s*[=:]\s*["\'][^"\']+["\']',
            r'-----BEGIN (RSA |EC )?PRIVATE KEY-----',
            r'(?i)bearer\s+[a-zA-Z0-9_\-\.]+',
        ]
        
        import re
        ext_list = extensions.split(',')
        
        output = "🔐 Detección de Secretos\n\n"
        findings = []
        
        for root, dirs, files in os.walk(path):
            # Skip hidden dirs and common non-code dirs
            dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['node_modules', '__pycache__', 'venv', '.git']]
            
            for file in files:
                if any(file.endswith(ext) for ext in ext_list):
                    filepath = os.path.join(root, file)
                    try:
                        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                        
                        for pattern in secret_patterns:
                            matches = re.findall(pattern, content)
                            for match in matches:
                                if len(match) > 5:  # Skip short matches
                                    findings.append({
                                        "file": filepath,
                                        "pattern": match[:50]
                                    })
                    except Exception:
                        pass
        
        if findings:
            output += f"⚠️ Encontrados {len(findings)} posibles secretos:\n\n"
            for f in findings[:20]:
                output += f"  📄 {f['file']}\n"
                output += f"     {f['pattern']}...\n\n"
        else:
            output += "✅ No se encontraron secretos obvios\n"
        
        return output
    
    except Exception as e:
        return f"Error escaneando: {e}"


# ── Task & Planning Implementations ─────────────────────────

def _log_analysis_handler(log_file: str, lines: int = 100, filter: str = None) -> str:
    """Analyze system logs."""
    try:
        log_file = os.path.expanduser(log_file)
        
        if not os.path.exists(log_file):
            return f"Error: Log no existe: {log_file}"
        
        with open(log_file, 'r', encoding='utf-8', errors='ignore') as f:
            all_lines = f.readlines()
        
        # Get last N lines
        log_lines = all_lines[-lines:]
        
        # Filter if specified
        if filter:
            log_lines = [l for l in log_lines if filter.upper() in l.upper()]
        
        output = f"📋 Análisis de {os.path.basename(log_file)}:\n\n"
        output += f"Líneas totales: {len(all_lines)}\n"
        output += f"Líneas analizadas: {len(log_lines)}\n\n"
        
        # Count by level
        from collections import Counter
        levels = Counter()
        for line in log_lines:
            if "ERROR" in line.upper():
                levels["ERROR"] += 1
            elif "WARN" in line.upper():
                levels["WARN"] += 1
            elif "INFO" in line.upper():
                levels["INFO"] += 1
            else:
                levels["OTHER"] += 1
        
        output += "Por nivel:\n"
        for level, count in levels.most_common():
            output += f"  {level}: {count}\n"
        
        # Show errors
        errors = [l.strip() for l in log_lines if "ERROR" in l.upper()]
        if errors:
            output += f"\nÚltimos errores:\n"
            for e in errors[:5]:
                output += f"  • {e[:200]}\n"
        
        return output
    
    except Exception as e:
        return f"Error analizando logs: {e}"



def _audit_get_metrics_handler(hours: int = 24) -> str:
    """Consulta métricas agregadas de rendimiento de herramientas, tasa de éxito y uso de GPU/VRAM."""
    try:
        from scripts.tools.audit_logger import AuditLogger
        logger = AuditLogger()
        metrics = logger.get_metrics(hours)

        output = f"📊 **Métricas de Ejecución AI Lab (Últimas {hours} horas)**\n\n"
        output += f"• **Total de Invocaciones**: {metrics['total_calls']}\n"
        output += f"• **Tasa de Éxito**: {metrics['success_rate_pct']}%\n"
        output += f"• **Latencia Promedio**: {metrics['avg_duration_ms']} ms (Máx: {metrics['max_duration_ms']} ms)\n"
        output += f"• **Tokens Estimados Procesados**: {metrics['total_tokens_estimate']}\n"
        output += f"• **Uso Promedio VRAM GPU**: {metrics['avg_gpu_vram_mb']} MB (Temp Máx: {metrics['max_gpu_temp_c']} °C)\n\n"

        if metrics.get("top_tools"):
            output += "🏆 **Herramientas más utilizadas:**\n"
            for t in metrics["top_tools"]:
                err_str = f" ({t['errors']} fallos)" if t["errors"] > 0 else ""
                output += f"  - `{t['tool']}`: {t['calls']} llamadas ({t['avg_duration_ms']} ms prom){err_str}\n"

        if metrics.get("recent_errors"):
            output += "\n⚠️ **Errores Recientes:**\n"
            for err in metrics["recent_errors"]:
                output += f"  - [{err['timestamp']}] `{err['tool']}`: {err['error']}\n"

        return output
    except Exception as e:
        return f"Error al recuperar métricas de auditoría: {e}"



def _audit_list_traces_handler(limit: int = 10, errors_only: bool = False) -> str:
    """Lista las últimas trazas de auditoría de ejecución de herramientas."""
    try:
        from scripts.tools.audit_logger import AuditLogger
        logger = AuditLogger()
        traces = logger.list_recent_traces(limit=limit, errors_only=errors_only)

        if not traces:
            return "ℹ️ No se encontraron trazas registradas en la base de datos de auditoría."

        output = f"📜 **Últimas {len(traces)} Trazas de Auditoría** (Filtro solo errores: {errors_only}):\n\n"
        for t in traces:
            icon = "✅" if t["success"] else "❌"
            output += f"{icon} **[#{t['id']} | {t['timestamp']}]** `{t['tool']}` — {t['duration_ms']} ms | VRAM: {t['vram_mb']} MB\n"
            if not t["success"] and t["error"]:
                output += f"   └── *Error:* {t['error']}\n"
        return output
    except Exception as e:
        return f"Error al listar trazas de auditoría: {e}"


# ── Declarative Workflow (DAG) Tools ────────────────────────

HANDLERS = {
    "security_audit": _security_audit_handler,
    "secret_detection": _secret_detection_handler,
    "log_analysis": _log_analysis_handler,
    "audit_get_metrics": _audit_get_metrics_handler,
    "audit_list_traces": _audit_list_traces_handler,
}
