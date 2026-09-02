"""Database, CSV, JSON, and data analysis tools"""

import os

import json
import csv
from datetime import datetime
from mcp_common.paths import HOME
from mcp_common.logging import log_operation

TOOLS = [
    {
        "name": "sql_query",
        "description": "Ejecuta query SQL en una base de datos SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Ruta de la DB SQLite (default: ai-memory.db)."
                },
                "query": {
                    "type": "string",
                    "description": "Query SQL a ejecutar."
                },
                "params": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Parámetros de la query."
                }
            },
            "required": ["query"]
        }
    },
    {
        "name": "backup_database",
        "description": "Crea backup de una base de datos SQLite.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "database": {
                    "type": "string",
                    "description": "Ruta de la DB a respaldar."
                },
                "backup_path": {
                    "type": "string",
                    "description": "Ruta del backup (default: auto-generada)."
                }
            },
            "required": ["database"]
        }
    },
    {
        "name": "csv_to_json",
        "description": "Convierte CSV a JSON.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Ruta del archivo CSV."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida JSON (opcional)."
                }
            },
            "required": ["input_file"]
        }
    },
    {
        "name": "json_to_csv",
        "description": "Convierte JSON a CSV.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Ruta del archivo JSON."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida CSV (opcional)."
                }
            },
            "required": ["input_file"]
        }
    },
    {
        "name": "convert_file",
        "description": "Convierte entre formatos: CSV, JSON, XML, YAML, Markdown.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "input_file": {
                    "type": "string",
                    "description": "Ruta del archivo de entrada."
                },
                "output_format": {
                    "type": "string",
                    "enum": ["csv", "json", "xml", "yaml", "md", "txt"],
                    "description": "Formato de salida."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida (opcional)."
                }
            },
            "required": ["input_file", "output_format"]
        }
    },
    {
        "name": "generate_csv",
        "description": "Genera archivo CSV desde datos estructurados.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "data": {
                    "type": "string",
                    "description": "Datos en formato JSON (array de objetos)."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida."
                },
                "delimiter": {
                    "type": "string",
                    "description": "Delimitador.",
                    "default": ","
                }
            },
            "required": ["data", "output_file"]
        }
    },
    {
        "name": "extract_pdf",
        "description": "Extrae texto de un archivo PDF.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pdf_path": {
                    "type": "string",
                    "description": "Ruta del PDF."
                },
                "pages": {
                    "type": "string",
                    "description": "Páginas a extraer (ej: '1-5', '1,3,5', 'all').",
                    "default": "all"
                }
            },
            "required": ["pdf_path"]
        }
    },
    {
        "name": "data_analysis",
        "description": "Análisis básico de datos: estadísticas, valores únicos, nulos.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Ruta del archivo (CSV o JSON)."
                },
                "column": {
                    "type": "string",
                    "description": "Columna específica a analizar."
                }
            },
            "required": ["file_path"]
        }
    },
    {
        "name": "generate_report",
        "description": "Genera reporte en Markdown con datos y análisis.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Título del reporte."
                },
                "sections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "heading": {"type": "string"},
                            "content": {"type": "string"},
                            "data": {"type": "array"}
                        }
                    },
                    "description": "Secciones del reporte."
                },
                "output_file": {
                    "type": "string",
                    "description": "Ruta de salida (opcional)."
                }
            },
            "required": ["title", "sections"]
        }
    },
]

# ── Handlers ───────────────────────────────────────────────
def _sql_query_handler(query: str, database: str = None, params: list = None) -> str:
    """Execute SQL query on SQLite database."""
    try:
        import sqlite3
        
        if not database:
            database = os.path.join(HOME, ".config/ai-memory.db")
        else:
            database = os.path.expanduser(database)
        
        if not os.path.exists(database):
            return f"Error: Base de datos no existe: {database}"
        
        conn = sqlite3.connect(database)
        cursor = conn.cursor()
        
        # Check if it's a SELECT query
        is_select = query.strip().upper().startswith("SELECT")
        
        if params:
            cursor.execute(query, params)
        else:
            cursor.execute(query)
        
        if is_select:
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            rows = cursor.fetchall()
            
            if not rows:
                return "Query ejecutada. Sin resultados."
            
            output = f"Resultados ({len(rows)} filas):\n\n"
            
            # Header
            output += " | ".join(columns) + "\n"
            output += "-" * 50 + "\n"
            
            # Rows
            for row in rows[:100]:  # Limit to 100 rows
                output += " | ".join(str(v) if v is not None else "NULL" for v in row) + "\n"
            
            if len(rows) > 100:
                output += f"\n... y {len(rows) - 100} filas más"
            
            return output
        else:
            conn.commit()
            affected = cursor.rowcount
            log_operation("sql_query", {"query": query[:100]}, f"affected:{affected}")
            return f"Query ejecutada. Filas afectadas: {affected}"
        
        conn.close()
    
    except Exception as e:
        return f"Error SQL: {e}"



def _backup_database_handler(database: str, backup_path: str = None) -> str:
    """Backup SQLite database."""
    try:
        import sqlite3

        database = os.path.expanduser(database)
        
        if not os.path.exists(database):
            return f"Error: Base de datos no existe: {database}"
        
        if not backup_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            db_name = os.path.basename(database).replace(".db", "")
            backup_dir = os.path.join(HOME, ".local/backups")
            os.makedirs(backup_dir, exist_ok=True)
            backup_path = os.path.join(backup_dir, f"{db_name}_{timestamp}.db")
        else:
            backup_path = os.path.expanduser(backup_path)
        
        # Use SQLite backup API
        source = sqlite3.connect(database)
        dest = sqlite3.connect(backup_path)
        source.backup(dest)
        source.close()
        dest.close()
        
        size = os.path.getsize(backup_path)
        log_operation("backup_database", {"database": database}, f"backup:{backup_path}")
        return f"Backup creado: {backup_path} ({size} bytes)"
    
    except Exception as e:
        return f"Error creando backup: {e}"


# ── Data Processing Implementations ─────────────────────────

def _csv_to_json_handler(input_file: str, output_file: str = None) -> str:
    """Convert CSV to JSON."""
    try:
        import csv
        
        input_file = os.path.expanduser(input_file)
        
        with open(input_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            data = list(reader)
        
        if not output_file:
            output_file = input_file.rsplit('.', 1)[0] + '.json'
        else:
            output_file = os.path.expanduser(output_file)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        log_operation("csv_to_json", {"input": input_file}, f"output:{output_file}")
        return f"Convertido: {output_file} ({len(data)} registros)"
    
    except Exception as e:
        return f"Error convirtiendo: {e}"



def _json_to_csv_handler(input_file: str, output_file: str = None) -> str:
    """Convert JSON to CSV."""
    try:
        import csv
        
        input_file = os.path.expanduser(input_file)
        
        with open(input_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        if not isinstance(data, list) or not data:
            return "Error: JSON debe ser un array de objetos"
        
        if not output_file:
            output_file = input_file.rsplit('.', 1)[0] + '.csv'
        else:
            output_file = os.path.expanduser(output_file)
        
        headers = data[0].keys()
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            writer.writerows(data)
        
        log_operation("json_to_csv", {"input": input_file}, f"output:{output_file}")
        return f"Convertido: {output_file} ({len(data)} registros)"
    
    except Exception as e:
        return f"Error convirtiendo: {e}"



def _convert_file_handler(input_file: str, output_format: str, output_file: str = None) -> str:
    """Convert between file formats."""
    try:
        import csv
        import xml.etree.ElementTree as ET
        import yaml
        
        input_file = os.path.expanduser(input_file)
        
        if not os.path.exists(input_file):
            return f"Error: Archivo no existe: {input_file}"
        
        # Read input
        ext = input_file.rsplit('.', 1)[-1].lower()
        
        with open(input_file, 'r', encoding='utf-8') as f:
            if ext == 'csv':
                data = list(csv.DictReader(f))
            elif ext == 'json':
                data = json.load(f)
            elif ext == 'xml':
                tree = ET.parse(f)
                root = tree.getroot()
                data = [{elem.tag: elem.text for elem in child} for child in root]
            elif ext == 'yaml' or ext == 'yml':
                data = yaml.safe_load(f)
            elif ext == 'md' or ext == 'txt':
                data = f.read()
            else:
                return f"Formato no soportado: {ext}"
        
        # Generate output
        if not output_file:
            output_file = input_file.rsplit('.', 1)[0] + '.' + output_format
        else:
            output_file = os.path.expanduser(output_file)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            if output_format == 'csv':
                if isinstance(data, list) and data:
                    writer = csv.DictWriter(f, fieldnames=data[0].keys())
                    writer.writeheader()
                    writer.writerows(data)
            elif output_format == 'json':
                json.dump(data, f, indent=2, ensure_ascii=False)
            elif output_format == 'xml':
                root = ET.Element("data")
                for item in data:
                    elem = ET.SubElement(root, "item")
                    for k, v in item.items():
                        child = ET.SubElement(elem, k)
                        child.text = str(v)
                ET.ElementTree(root).write(f, encoding='unicode')
            elif output_format == 'yaml':
                yaml.dump(data, f, allow_unicode=True)
            elif output_format == 'md':
                if isinstance(data, list) and data:
                    f.write("| " + " | ".join(data[0].keys()) + " |\n")
                    f.write("|" + "|".join(["---"] * len(data[0])) + "|\n")
                    for row in data:
                        f.write("| " + " | ".join(str(v) for v in row.values()) + " |\n")
            elif output_format == 'txt':
                f.write(str(data))
        
        log_operation("convert_file", {"input": input_file}, f"output:{output_file}")
        return f"Convertido: {output_file}"
    
    except Exception as e:
        return f"Error convirtiendo: {e}"



def _generate_csv_handler(data: str, output_file: str, delimiter: str = ",") -> str:
    """Generate CSV from JSON data."""
    try:
        import csv
        
        # Parse data
        if isinstance(data, str):
            rows = json.loads(data)
        else:
            rows = data
        
        if not isinstance(rows, list) or not rows:
            return "Error: Datos deben ser un array de objetos"
        
        output_file = os.path.expanduser(output_file)
        
        with open(output_file, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys(), delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
        
        log_operation("generate_csv", {"rows": len(rows)}, f"output:{output_file}")
        return f"CSV generado: {output_file} ({len(rows)} filas)"
    
    except Exception as e:
        return f"Error generando CSV: {e}"



def _extract_pdf_handler(pdf_path: str, pages: str = "all") -> str:
    """Extract text from PDF."""
    try:
        from PyPDF2 import PdfReader
        
        pdf_path = os.path.expanduser(pdf_path)
        
        if not os.path.exists(pdf_path):
            return f"Error: PDF no existe: {pdf_path}"
        
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        
        # Parse pages to extract
        if pages == "all":
            page_indices = range(total_pages)
        else:
            page_indices = []
            for part in pages.split(","):
                if "-" in part:
                    start, end = part.split("-")
                    page_indices.extend(range(int(start) - 1, int(end)))
                else:
                    page_indices.append(int(part) - 1)
        
        output = f"📄 PDF: {os.path.basename(pdf_path)} ({total_pages} páginas)\n\n"
        
        for i in page_indices:
            if i < total_pages:
                text = reader.pages[i].extract_text()
                output += f"--- Página {i + 1} ---\n{text}\n\n"
        
        return output[:5000]
    
    except ImportError:
        return "Error: PyPDF2 no instalado"
    except Exception as e:
        return f"Error extrayendo PDF: {e}"



def _data_analysis_handler(file_path: str, column: str = None) -> str:
    """Basic data analysis."""
    try:
        import csv
        
        file_path = os.path.expanduser(file_path)
        
        if not os.path.exists(file_path):
            return f"Error: Archivo no existe: {file_path}"
        
        ext = file_path.rsplit('.', 1)[-1].lower()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            if ext == 'csv':
                data = list(csv.DictReader(f))
            elif ext == 'json':
                data = json.load(f)
            else:
                return f"Formato no soportado: {ext}"
        
        if not data:
            return "Sin datos para analizar"
        
        output = f"📊 Análisis de {os.path.basename(file_path)}:\n\n"
        output += f"Total registros: {len(data)}\n"
        output += f"Columnas: {', '.join(data[0].keys())}\n\n"
        
        if column and column in data[0]:
            values = [row[column] for row in data if row.get(column)]
            
            # Try numeric analysis
            try:
                nums = [float(v) for v in values if v]
                output += f"📊 Análisis de '{column}':\n"
                output += f"  Min: {min(nums)}\n"
                output += f"  Max: {max(nums)}\n"
                output += f"  Promedio: {sum(nums) / len(nums):.2f}\n"
                output += f"  Valores únicos: {len(set(values))}\n"
            except ValueError:
                # Text analysis
                output += f"📊 Análisis de '{column}':\n"
                output += f"  Valores únicos: {len(set(values))}\n"
                from collections import Counter
                counts = Counter(values)
                output += f"  Más comunes: {counts.most_common(5)}\n"
        
        # Check for nulls
        nulls = sum(1 for row in data if any(not v for v in row.values()))
        output += f"\nRegistros con valores vacíos: {nulls}\n"
        
        return output
    
    except Exception as e:
        return f"Error analizando: {e}"


# ── Log & System Implementations ────────────────────────────

def _generate_report_handler(title: str, sections: list, output_file: str = None) -> str:
    """Generate Markdown report."""
    try:
        output = f"# {title}\n\n"
        output += f"*Generado: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n\n"
        
        for section in sections:
            heading = section.get("heading", "")
            content = section.get("content", "")
            data = section.get("data", [])
            
            if heading:
                output += f"## {heading}\n\n"
            
            if content:
                output += f"{content}\n\n"
            
            if data:
                if isinstance(data, list) and data and isinstance(data[0], dict):
                    # Table
                    headers = data[0].keys()
                    output += "| " + " | ".join(headers) + " |\n"
                    output += "|" + "|".join(["---"] * len(headers)) + "|\n"
                    for row in data:
                        output += "| " + " | ".join(str(v) for v in row.values()) + " |\n"
                    output += "\n"
                elif isinstance(data, list):
                    # List
                    for item in data:
                        output += f"- {item}\n"
                    output += "\n"
        
        if output_file:
            output_file = os.path.expanduser(output_file)
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(output)
            return f"Reporte generado: {output_file}"
        
        return output
    
    except Exception as e:
        return f"Error generando reporte: {e}"


# ── Security Implementations ────────────────────────────────

HANDLERS = {
    "sql_query": _sql_query_handler,
    "backup_database": _backup_database_handler,
    "csv_to_json": _csv_to_json_handler,
    "json_to_csv": _json_to_csv_handler,
    "convert_file": _convert_file_handler,
    "generate_csv": _generate_csv_handler,
    "extract_pdf": _extract_pdf_handler,
    "data_analysis": _data_analysis_handler,
    "generate_report": _generate_report_handler,
}
