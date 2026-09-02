import json
import html
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from src.database import get_db
from src.services.chat_service import ChatService
from src.services.token_service import TokenService

router = APIRouter()


def _render_chat_html(title: str, messages: list, metadata: dict, created_at: str, version: int) -> str:
    escaped_title = html.escape(title or "Chat Compartido")
    chat_json = json.dumps({
        "title": title,
        "messages": messages,
        "metadata": metadata,
        "created_at": created_at,
        "version": version
    }, ensure_ascii=False)

    return f"""<!DOCTYPE html>
<html lang="es" class="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{escaped_title} — AI Lab ChatShare</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/styles/github-dark.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        brand: {{
                            50: '#eef2ff',
                            400: '#818cf8',
                            500: '#6366f1',
                            600: '#4f46e5',
                            700: '#4338ca',
                            900: '#312e81',
                            950: '#1e1b4b'
                        }}
                    }}
                }}
            }}
        }}
    </script>
    <style>
        .prose pre {{ background-color: #090d16 !important; border: 1px solid #1e293b; border-radius: 0.75rem; }}
        .prose code {{ color: #38bdf8; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; }}
        .prose p {{ margin-bottom: 0.75rem; }}
        .prose p:last-child {{ margin-bottom: 0; }}
        .prose ul, .prose ol {{ margin-left: 1.25rem; margin-bottom: 0.75rem; }}
        .prose ul {{ list-style-type: disc; }}
        .prose ol {{ list-style-type: decimal; }}
        details[open] summary svg.chevron {{ transform: rotate(180deg); }}
        
        /* Audio Player Styling */
        audio::-webkit-media-controls-panel {{
            background-color: #1e293b;
        }}
        audio::-webkit-media-controls-current-time-display,
        audio::-webkit-media-controls-time-remaining-display {{
            color: #cbd5e1;
        }}
        
        /* Custom scrollbar */
        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: #020617; }}
        ::-webkit-scrollbar-thumb {{ background: #1e293b; border-radius: 4px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #334155; }}
    </style>
</head>
<body class="bg-slate-950 text-slate-100 min-h-screen flex flex-col font-sans antialiased selection:bg-indigo-500 selection:text-white">
    <!-- Header -->
    <header class="border-b border-slate-800/80 bg-slate-900/90 backdrop-blur sticky top-0 z-40 shadow-sm">
        <div class="max-w-4xl mx-auto px-4 py-3 flex flex-wrap items-center justify-between gap-3">
            <div class="flex items-center space-x-3">
                <a href="https://github.com/dantecc10/ai-lab" target="_blank" rel="noopener noreferrer" class="group block relative">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 via-purple-600 to-cyan-400 flex items-center justify-center shadow-lg shadow-indigo-500/20 group-hover:scale-105 transition-transform duration-200">
                        <svg class="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                        </svg>
                    </div>
                </a>
                <div>
                    <h1 class="font-bold text-base md:text-lg text-slate-100 leading-tight flex items-center gap-2">
                        <span>{escaped_title}</span>
                    </h1>
                    <div class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-400">
                        <span class="text-indigo-400 font-semibold">Autor: Dante Castelán Carpinteyro</span>
                        <span>•</span>
                        <span>v{version}</span>
                        <span>•</span>
                        <span>{created_at[:10] if created_at else ""}</span>
                        <span>•</span>
                        <span class="inline-flex items-center text-emerald-400 font-medium">
                            <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1 animate-pulse"></span>
                            AI Lab Sync
                        </span>
                    </div>
                </div>
            </div>

            <!-- Action Controls & Links -->
            <div class="flex flex-wrap items-center gap-2">
                <!-- GitHub Repo Link -->
                <a href="https://github.com/dantecc10/ai-lab" target="_blank" rel="noopener noreferrer" 
                   class="px-3 py-1.5 text-xs font-semibold bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition-all flex items-center space-x-1.5 shadow-sm hover:border-slate-600">
                    <svg class="w-4 h-4 text-slate-300 fill-current" viewBox="0 0 24 24">
                        <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                    </svg>
                    <span>GitHub</span>
                    <span class="text-[10px] bg-slate-700/80 px-1.5 py-0.2 rounded text-slate-300">dantecc10</span>
                </a>

                <!-- Tech Blueprint Drawer Button -->
                <button onclick="toggleTechModal()" class="px-3 py-1.5 text-xs font-semibold bg-cyan-950/80 hover:bg-cyan-900 text-cyan-300 border border-cyan-700/60 rounded-lg transition-colors flex items-center space-x-1.5 shadow-sm" title="Ver especificaciones técnicas y arquitectura de AI Lab">
                    <span>🔬</span>
                    <span>Arquitectura</span>
                </button>

                <!-- Verbose / Minimal Toggle -->
                <button onclick="toggleVerboseMode()" id="verboseBtn" class="px-3 py-1.5 text-xs font-semibold bg-indigo-950/80 hover:bg-indigo-900 text-indigo-300 border border-indigo-700/60 rounded-lg transition-colors flex items-center space-x-1.5" title="Alternar entre ver todo el razonamiento y planning o vista minimal">
                    <span id="verboseIcon">🧠</span>
                    <span id="verboseText">Modo Detallado</span>
                </button>

                <!-- QR Modal Button -->
                <button onclick="toggleQRModal()" class="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition-colors flex items-center space-x-1.5">
                    <svg class="w-3.5 h-3.5 text-slate-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v1m6 11h2m-6 0h-2v4m0-11v3m0 0h.01M12 12h4.01M16 20h4M4 12h4m12 0h.01M5 8h2a1 1 0 001-1V5a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1zm12 0h2a1 1 0 001-1V5a1 1 0 00-1-1h-2a1 1 0 00-1 1v2a1 1 0 001 1zM5 20h2a1 1 0 001-1v-2a1 1 0 00-1-1H5a1 1 0 00-1 1v2a1 1 0 001 1z" />
                    </svg>
                    <span>QR</span>
                </button>

                <!-- Copy Link Button -->
                <button onclick="copyCurrentUrl()" id="copyBtn" class="px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 rounded-lg transition-colors flex items-center space-x-1.5">
                    <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <span>Copiar</span>
                </button>
            </div>
        </div>

        <!-- Dynamic Statistics & Model Pill Bar -->
        <div class="border-t border-slate-800/60 bg-slate-950/70 px-4 py-2">
            <div class="max-w-4xl mx-auto flex flex-wrap items-center justify-between gap-2 text-[11px] text-slate-400">
                <div class="flex flex-wrap items-center gap-3" id="statsBarContainer">
                    <span class="inline-flex items-center gap-1.5 text-indigo-300 font-medium">
                        <span>🤖</span>
                        <span id="modelBadge">Gemma 4 12B IT (64k Context)</span>
                    </span>
                    <span class="text-slate-600">|</span>
                    <span class="inline-flex items-center gap-1">
                        <span>⚡</span>
                        <span>NVIDIA RTX 5060 + Pop!_OS</span>
                    </span>
                    <span class="text-slate-600">|</span>
                    <span id="msgCountBadge" class="text-slate-300 font-medium">-- mensajes</span>
                    <span id="thoughtsBadge" class="text-purple-300 font-medium">-- pensamientos</span>
                    <span id="toolsBadge" class="text-cyan-300 font-medium">-- herramientas</span>
                </div>
                <div class="flex items-center gap-2">
                    <span id="readingTimeBadge" class="text-slate-400">⏱️ ~-- min lectura</span>
                </div>
            </div>
        </div>
    </header>

    <!-- Technical Architecture Modal -->
    <div id="techModal" class="hidden fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4">
        <div class="bg-slate-900 border border-slate-700/80 rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto">
            <div class="flex items-start justify-between">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-600 to-indigo-600 flex items-center justify-center shadow-md">
                        <span class="text-xl">🔬</span>
                    </div>
                    <div>
                        <h3 class="font-bold text-slate-100 text-lg">AI Lab — Arquitectura Técnica</h3>
                        <p class="text-xs text-slate-400">Ecosistema Local Autónomo de Inteligencia Artificial</p>
                    </div>
                </div>
                <button onclick="toggleTechModal()" class="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition">
                    <svg class="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>

            <!-- Architecture Grid -->
            <div class="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                <!-- Card 1: Hardware & Engine -->
                <div class="p-3.5 bg-slate-950/80 border border-slate-800 rounded-xl space-y-1.5">
                    <div class="font-bold text-indigo-400 flex items-center gap-1.5 text-xs">
                        <span>⚡</span>
                        <span>Motor de Inferencia Local</span>
                    </div>
                    <p class="text-slate-300 leading-relaxed">
                        Ejecutado con <strong>llama.cpp</strong> sobre GPU dedicada <strong>NVIDIA GeForce RTX 5060 (8GB VRAM)</strong> y CPU AMD Ryzen 7 (16 hilos) en Pop!_OS 24.04.
                    </p>
                    <div class="text-[10px] text-slate-500 font-mono">Flash Attention • Q8_0 KV Cache • 64k Tokens Nativo</div>
                </div>

                <!-- Card 2: Model & Reasoning -->
                <div class="p-3.5 bg-slate-950/80 border border-slate-800 rounded-xl space-y-1.5">
                    <div class="font-bold text-purple-400 flex items-center gap-1.5 text-xs">
                        <span>🧠</span>
                        <span>Modelo & Razonamiento</span>
                    </div>
                    <p class="text-slate-300 leading-relaxed">
                        <strong>Gemma 4 12B IT</strong> con separación nativa de cadenas de razonamiento (<code>&lt;thought&gt;</code>) y respuestas finales estructuradas.
                    </p>
                    <div class="text-[10px] text-slate-500 font-mono">Thinking Preservado • Inferencia 100% Privada</div>
                </div>

                <!-- Card 3: MCP & Extensibility -->
                <div class="p-3.5 bg-slate-950/80 border border-slate-800 rounded-xl space-y-1.5">
                    <div class="font-bold text-cyan-400 flex items-center gap-1.5 text-xs">
                        <span>🔌</span>
                        <span>Protocolo MCP (Model Context Protocol)</span>
                    </div>
                    <p class="text-slate-300 leading-relaxed">
                        Servidor Stdio con <strong>150+ herramientas locales</strong>: auditoría de red L2/L3/L4 sin root, visión multimodal, OCR Tesseract, bash seguro y control domótico Kasa.
                    </p>
                    <div class="text-[10px] text-slate-500 font-mono">Tool Calling Asíncrono • Audit Traces JSON</div>
                </div>

                <!-- Card 4: Cognitive Memory 2.0 -->
                <div class="p-3.5 bg-slate-950/80 border border-slate-800 rounded-xl space-y-1.5">
                    <div class="font-bold text-emerald-400 flex items-center gap-1.5 text-xs">
                        <span>🧬</span>
                        <span>Memoria Cognitiva 2.0 & JIT Graph</span>
                    </div>
                    <p class="text-slate-300 leading-relaxed">
                        Grafo de conocimiento relacional JIT (&lt;1ms), memoria episódica vectorial y compactación de contexto con modelo satélite E4B.
                    </p>
                    <div class="text-[10px] text-slate-500 font-mono">Sin Bloat de Contexto • Decaimiento Temporal</div>
                </div>
            </div>

            <!-- Author & Open Source Footer -->
            <div class="p-4 bg-indigo-950/30 border border-indigo-800/40 rounded-xl flex flex-col sm:flex-row items-center justify-between gap-3 text-xs">
                <div>
                    <div class="font-bold text-slate-200">Desarrollado y Diseñado por:</div>
                    <div class="text-indigo-300 font-semibold">Dante Castelán Carpinteyro</div>
                </div>
                <a href="https://github.com/dantecc10/ai-lab" target="_blank" rel="noopener noreferrer" 
                   class="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-lg transition shadow-md flex items-center gap-2">
                    <svg class="w-4 h-4 fill-current" viewBox="0 0 24 24">
                        <path fill-rule="evenodd" clip-rule="evenodd" d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.53 1.032 1.53 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
                    </svg>
                    <span>Ver Código en GitHub</span>
                </a>
            </div>
        </div>
    </div>

    <!-- QR Modal -->
    <div id="qrModal" class="hidden fixed inset-0 z-50 bg-black/75 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-slate-900 border border-slate-700 rounded-2xl p-6 max-w-sm w-full text-center shadow-2xl space-y-4">
            <h3 class="font-bold text-slate-100 text-base">Escanea para abrir en tu celular</h3>
            <div class="bg-white p-4 rounded-xl inline-block shadow-inner">
                <img id="qrImage" src="" alt="QR Code" class="w-48 h-48 mx-auto" />
            </div>
            <p class="text-xs text-slate-400">Acceso directo al chat público con token de seguridad.</p>
            <button onclick="toggleQRModal()" class="w-full py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl text-xs font-semibold border border-slate-700 transition">Cerrar</button>
        </div>
    </div>

    <!-- Image Lightbox Modal -->
    <div id="imageLightbox" onclick="closeLightbox()" class="hidden fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-4 cursor-zoom-out">
        <img id="lightboxImg" src="" alt="Ampliada" class="max-w-full max-h-[90vh] rounded-xl shadow-2xl object-contain" />
    </div>

    <!-- Main Container -->
    <main class="flex-1 max-w-4xl w-full mx-auto p-4 md:py-8 space-y-6">
        <div id="messagesContainer" class="space-y-6">
            <!-- Messages rendered by JS -->
        </div>
    </main>

    <!-- Footer -->
    <footer class="border-t border-slate-800/80 bg-slate-900/40 py-6 mt-12 text-center text-xs text-slate-500">
        <div class="max-w-4xl mx-auto px-4 flex flex-col sm:flex-row items-center justify-between gap-3">
            <div class="flex items-center space-x-2">
                <span class="w-2 h-2 rounded-full bg-indigo-500"></span>
                <p>AI Lab — Desarrollado por <strong class="text-slate-300 font-medium">Dante Castelán Carpinteyro</strong></p>
            </div>
            <div class="flex items-center space-x-4">
                <a href="https://github.com/dantecc10/ai-lab" target="_blank" rel="noopener noreferrer" class="text-indigo-400 hover:text-indigo-300 font-medium transition">
                    github.com/dantecc10/ai-lab
                </a>
                <span class="text-slate-700">|</span>
                <span class="text-slate-500 font-mono">ai.castelancarpinteyro.com</span>
            </div>
        </div>
    </footer>

    <script id="chat-data" type="application/json">
        {chat_json}
    </script>

    <script>
        const chatData = JSON.parse(document.getElementById('chat-data').textContent);
        const container = document.getElementById('messagesContainer');
        let isVerboseMode = true; // Verbose por defecto

        // Configure Marked Renderer with Smart Multimedia Auto-Detection
        const renderer = new marked.Renderer();

        function extractMediaInfo(arg1, arg2, arg3) {{
            if (typeof arg1 === 'object' && arg1 !== null) {{
                return {{
                    href: arg1.href || '',
                    title: arg1.title || '',
                    text: arg1.text || ''
                }};
            }}
            return {{
                href: typeof arg1 === 'string' ? arg1 : '',
                title: typeof arg2 === 'string' ? arg2 : '',
                text: typeof arg3 === 'string' ? arg3 : (typeof arg1 === 'string' ? arg1 : '')
            }};
        }}

        // Custom image rendering with lightbox click support
        renderer.image = function(arg1, arg2, arg3) {{
            const {{ href, text }} = extractMediaInfo(arg1, arg2, arg3);
            const alt = text || 'Imagen adjunta';
            return `
            <div class="my-3 group relative inline-block max-w-full">
                <img src="${{href}}" alt="${{alt}}" loading="lazy" onclick="openLightbox('${{href}}')" 
                     class="rounded-xl border border-slate-700/80 max-h-96 max-w-full object-contain cursor-zoom-in shadow-md transition-transform duration-200 group-hover:brightness-105 bg-slate-900/60" />
                ${{text ? `<span class="block text-[11px] text-slate-400 mt-1 italic">${{htmlEscape(text)}}</span>` : ''}}
            </div>`;
        }};

        // Custom link rendering that detects Audio, Video, Image, and normal links
        renderer.link = function(arg1, arg2, arg3) {{
            const {{ href, text }} = extractMediaInfo(arg1, arg2, arg3);
            if (!href) return text || '';
            const lower = href.toLowerCase();

            // Video formats
            if (lower.match(/\\.(mp4|webm|mov|mkv)(\\?.*)?$/) || lower.startsWith('data:video/')) {{
                return `
                <div class="my-3 rounded-xl overflow-hidden border border-slate-700/80 bg-slate-950 shadow-md">
                    <video controls playsinline preload="metadata" class="w-full max-h-96 object-contain bg-black">
                        <source src="${{href}}">
                        Tu navegador no soporta reproducción de video.
                    </video>
                    ${{text ? `<div class="p-2 text-xs text-slate-400 bg-slate-900 border-t border-slate-800">${{htmlEscape(text)}}</div>` : ''}}
                </div>`;
            }}

            // Audio formats
            if (lower.match(/\\.(mp3|wav|ogg|m4a|aac|flac)(\\?.*)?$/) || lower.startsWith('data:audio/')) {{
                return `
                <div class="my-3 p-3 bg-slate-900/90 border border-slate-700/70 rounded-xl shadow-sm flex flex-col sm:flex-row items-start sm:items-center gap-3">
                    <div class="w-8 h-8 rounded-lg bg-indigo-600/30 border border-indigo-500/40 flex items-center justify-center flex-shrink-0 text-indigo-400">
                        🎵
                    </div>
                    <div class="flex-1 w-full min-w-0">
                        ${{text && text !== href ? `<div class="text-xs font-semibold text-slate-200 mb-1.5 truncate">${{htmlEscape(text)}}</div>` : ''}}
                        <audio controls preload="metadata" class="w-full h-8 rounded">
                            <source src="${{href}}">
                            Tu navegador no soporta reproducción de audio.
                        </audio>
                    </div>
                </div>`;
            }}

            // Images / GIFs linked as normal links
            if (lower.match(/\\.(png|jpg|jpeg|gif|webp|svg)(\\?.*)?$/) || lower.startsWith('data:image/')) {{
                return renderer.image(arg1, arg2, arg3);
            }}

            return `<a href="${{href}}" target="_blank" rel="noopener noreferrer" class="text-indigo-400 hover:text-indigo-300 underline underline-offset-2 transition-colors">${{text || href}}</a>`;
        }};

        marked.setOptions({{
            renderer: renderer,
            highlight: function(code, lang) {{
                if (lang && hljs.getLanguage(lang)) {{
                    try {{ return hljs.highlight(code, {{ language: lang }}).value; }} catch(e) {{}}
                }}
                return hljs.highlightAuto(code).value;
            }},
            breaks: true
        }});

        function toggleTechModal() {{
            const modal = document.getElementById('techModal');
            modal.classList.toggle('hidden');
        }}

        function toggleVerboseMode() {{
            isVerboseMode = !isVerboseMode;
            const btn = document.getElementById('verboseBtn');
            const icon = document.getElementById('verboseIcon');
            const text = document.getElementById('verboseText');

            if (isVerboseMode) {{
                btn.className = "px-3 py-1.5 text-xs font-semibold bg-indigo-950/80 hover:bg-indigo-900 text-indigo-300 border border-indigo-700/60 rounded-lg transition-colors flex items-center space-x-1.5";
                icon.textContent = "🧠";
                text.textContent = "Modo Detallado";
            }} else {{
                btn.className = "px-3 py-1.5 text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 rounded-lg transition-colors flex items-center space-x-1.5";
                icon.textContent = "💬";
                text.textContent = "Modo Minimal";
            }}
            renderMessages();
        }}

        function toggleQRModal() {{
            const modal = document.getElementById('qrModal');
            const img = document.getElementById('qrImage');
            const currentUrl = encodeURIComponent(window.location.href);
            img.src = `https://api.qrserver.com/v1/create-qr-code/?size=250x250&margin=10&data=${{currentUrl}}`;
            modal.classList.toggle('hidden');
        }}

        function openLightbox(src) {{
            const modal = document.getElementById('imageLightbox');
            const img = document.getElementById('lightboxImg');
            img.src = src;
            modal.classList.remove('hidden');
        }}

        function closeLightbox() {{
            document.getElementById('imageLightbox').classList.add('hidden');
        }}

        function extractThinkingAndClean(text) {{
            if (typeof text !== 'string') return {{ thinking: null, clean: JSON.stringify(text) }};
            
            let thinking = null;
            let clean = text;

            // Pattern <thought>...</thought> or <thinking>...</thinking>
            const match = clean.match(/<(thought|thinking)>([^]*?)<\\/\\1>/i);
            if (match) {{
                thinking = match[2].trim();
                clean = clean.replace(match[0], '').trim();
            }}

            return {{ thinking, clean }};
        }}

        function updateStatistics(msgs) {{
            let thoughtCount = 0;
            let toolCount = 0;
            let totalWords = 0;

            msgs.forEach(m => {{
                if (m.thinking || m.thought || m.reasoning_content) thoughtCount++;
                if (m.tool_calls && m.tool_calls.length > 0) toolCount += m.tool_calls.length;
                if (typeof m.content === 'string') {{
                    totalWords += m.content.trim().split(' ').length;
                }}
            }});

            const readingMinutes = Math.max(1, Math.round(totalWords / 180));

            const msgBadge = document.getElementById('msgCountBadge');
            const thoughtsBadge = document.getElementById('thoughtsBadge');
            const toolsBadge = document.getElementById('toolsBadge');
            const readingTimeBadge = document.getElementById('readingTimeBadge');

            if (msgBadge) msgBadge.textContent = `💬 ${{msgs.length}} mensajes`;
            if (thoughtsBadge) thoughtsBadge.textContent = `🧠 ${{thoughtCount}} pensamientos`;
            if (toolsBadge) toolsBadge.textContent = `🛠️ ${{toolCount}} herramientas`;
            if (readingTimeBadge) readingTimeBadge.textContent = `⏱️ ~${{readingMinutes}} min lectura`;
        }}

        function renderMessages() {{
            const msgs = chatData.messages || [];
            updateStatistics(msgs);

            if (msgs.length === 0) {{
                container.innerHTML = '<div class="text-center py-12 text-slate-500">No hay mensajes en esta conversación.</div>';
                return;
            }}

            container.innerHTML = msgs.map((msg, idx) => {{
                const role = msg.role || 'assistant';
                const isUser = role === 'user';
                const isSystem = role === 'system';
                const isInterrupted = msg.status === 'interrupted' || msg.interrupted === true;

                // Extract thinking/reasoning if present in object or embedded in content
                let thinking = msg.thinking || msg.thought || msg.reasoning_content || null;
                let rawContent = typeof msg.content === 'string' ? msg.content : (msg.content ? JSON.stringify(msg.content) : '');

                if (!thinking && typeof rawContent === 'string') {{
                    const extracted = extractThinkingAndClean(rawContent);
                    thinking = extracted.thinking;
                    rawContent = extracted.clean;
                }}

                // Tool calls / Planning
                const toolCalls = msg.tool_calls || msg.tools || [];
                const planning = msg.planning || msg.plan || null;

                if (isSystem) {{
                    if (!isVerboseMode) return ''; // Hide system in minimal mode
                    return `
                    <div class="flex justify-center my-3">
                        <div class="bg-slate-900/90 border border-slate-800 text-slate-400 text-xs px-4 py-2 rounded-full max-w-xl text-center shadow-sm">
                            <span class="text-slate-500 font-semibold uppercase text-[10px] mr-1.5">⚙️ Sistema:</span> ${{htmlEscape(rawContent)}}
                        </div>
                    </div>`;
                }}

                const parsedContent = marked.parse(rawContent || (isInterrupted ? '*[Mensaje interrumpido antes de completar]*' : ''));

                // Verbose components
                let verboseHtml = '';
                if (isVerboseMode) {{
                    if (planning) {{
                        verboseHtml += `
                        <div class="mb-3 p-3 bg-amber-950/30 border border-amber-800/40 rounded-xl text-xs text-amber-200/90">
                            <div class="font-bold flex items-center space-x-1 text-amber-400 uppercase tracking-wider text-[10px] mb-1">
                                <span>📋 Planificación / Estrategia</span>
                            </div>
                            <div class="prose prose-invert prose-xs text-amber-100/90">${{marked.parse(planning)}}</div>
                        </div>`;
                    }}

                    if (thinking) {{
                        verboseHtml += `
                        <details class="mb-3 rounded-xl border border-purple-800/40 bg-purple-950/20 text-xs text-purple-200 overflow-hidden" open>
                            <summary class="cursor-pointer px-3.5 py-2 bg-purple-950/40 hover:bg-purple-900/40 font-semibold flex items-center justify-between select-none text-purple-300 text-[11px]">
                                <span class="flex items-center space-x-1.5">
                                    <span>🧠 Razonamiento / Cadena de Pensamiento</span>
                                </span>
                                <svg class="chevron w-3.5 h-3.5 transition-transform duration-200 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                                </svg>
                            </summary>
                            <div class="p-3.5 prose prose-invert prose-xs text-purple-200/90 max-w-none border-t border-purple-800/20 leading-relaxed font-mono whitespace-pre-wrap">${{htmlEscape(thinking)}}</div>
                        </details>`;
                    }}

                    if (toolCalls && toolCalls.length > 0) {{
                        verboseHtml += `
                        <div class="mb-3 space-y-2">
                            ${{toolCalls.map(tc => {{
                                const name = tc.name || (tc.function ? tc.function.name : 'tool');
                                const args = tc.arguments || (tc.function ? tc.function.arguments : '{{}}');
                                const argsStr = typeof args === 'string' ? args : JSON.stringify(args, null, 2);
                                return `
                                <details class="rounded-xl border border-cyan-800/40 bg-cyan-950/20 text-xs text-cyan-200 overflow-hidden">
                                    <summary class="cursor-pointer px-3.5 py-2 bg-cyan-950/40 hover:bg-cyan-900/40 font-semibold flex items-center justify-between text-cyan-300 text-[11px]">
                                        <span class="flex items-center space-x-1.5">
                                            <span>🛠️ Herramienta Ejecutada: <strong>${{name}}</strong></span>
                                        </span>
                                        <svg class="chevron w-3.5 h-3.5 transition-transform duration-200 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                                        </svg>
                                    </summary>
                                    <div class="p-3 bg-slate-950 font-mono text-[11px] text-cyan-300/90 overflow-x-auto border-t border-cyan-800/20">
                                        <pre class="!bg-transparent !p-0 !border-0">${{htmlEscape(argsStr)}}</pre>
                                    </div>
                                </details>`;
                            }}).join('')}}
                        </div>`;
                    }}
                }}

                const interruptedBadge = isInterrupted ? `
                <span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold bg-rose-900/60 text-rose-300 border border-rose-700/50 ml-2">
                    ⚠️ Interrumpido
                </span>` : '';

                return `
                <div class="flex gap-3 md:gap-4 ${{isUser ? 'flex-row-reverse' : ''}}">
                    <div class="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold ${{
                        isUser 
                            ? 'bg-indigo-600 text-white shadow-md shadow-indigo-500/20' 
                            : 'bg-gradient-to-tr from-cyan-600 to-blue-600 text-white shadow-md shadow-cyan-500/20'
                    }}">
                        ${{isUser ? 'Tú' : 'IA'}}
                    </div>
                    <div class="max-w-[88%] md:max-w-[82%] rounded-2xl px-4 py-3.5 ${{
                        isUser 
                            ? 'bg-indigo-600/20 text-indigo-100 border border-indigo-500/30' 
                            : 'bg-slate-900 text-slate-200 border border-slate-800 shadow-sm'
                    }}">
                        <div class="flex items-center justify-between text-[11px] font-semibold tracking-wide uppercase mb-1.5 ${{isUser ? 'text-indigo-300' : 'text-cyan-400'}}">
                            <span>${{isUser ? 'Dante Castelán (Usuario)' : 'Gemma 4 (Asistente AI Lab)'}}</span>
                            ${{interruptedBadge}}
                        </div>

                        ${{verboseHtml}}

                        <div class="prose prose-invert prose-sm max-w-none text-slate-200 leading-relaxed break-words">
                            ${{parsedContent}}
                        </div>
                    </div>
                </div>`;
            }}).join('');
        }}

        function htmlEscape(str) {{
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }}

        function copyCurrentUrl() {{
            navigator.clipboard.writeText(window.location.href);
            const btn = document.getElementById('copyBtn');
            const original = btn.innerHTML;
            btn.innerHTML = '<span>¡Copiado!</span>';
            btn.classList.add('bg-indigo-600', 'text-white');
            setTimeout(() => {{
                btn.innerHTML = original;
                btn.classList.remove('bg-indigo-600', 'text-white');
            }}, 2000);
        }}

        try {{
            renderMessages();
        }} catch(e) {{
            console.error("Error al renderizar mensajes:", e);
        }}

        document.addEventListener('DOMContentLoaded', () => {{
            try {{
                renderMessages();
            }} catch(e) {{}}
        }});
    </script>
</body>
</html>
"""


@router.get("/view/{chat_id}")
async def view_chat(
    chat_id: str,
    token: str,
    request: Request,
    format: str = None,
    db: AsyncSession = Depends(get_db)
):
    token_svc = TokenService(db)
    token_obj = await token_svc.validate_token(token)
    if not token_obj:
        raise HTTPException(401, "Token de acceso inválido, expirado o revocado.")
    if token_obj.chat_id != chat_id:
        raise HTTPException(403, "El token no corresponde a este chat.")

    chat_svc = ChatService(db)
    chat = await chat_svc.get_chat(chat_id)
    if not chat or chat.is_deleted:
        raise HTTPException(404, "Chat no encontrado.")

    messages = json.loads(chat.messages) if isinstance(chat.messages, str) else chat.messages
    metadata = json.loads(chat.metadata_) if isinstance(chat.metadata_, str) else chat.metadata_
    created_at_str = chat.created_at.isoformat() if chat.created_at else ""

    # Return JSON if requested
    accept_header = request.headers.get("accept", "")
    if format == "json" or ("application/json" in accept_header and "text/html" not in accept_header):
        return {
            "id": chat.id,
            "title": chat.title,
            "messages": messages,
            "metadata": metadata,
            "version": chat.version,
            "created_at": created_at_str,
        }

    # Otherwise render HTML
    html_content = _render_chat_html(
        title=chat.title,
        messages=messages,
        metadata=metadata,
        created_at=created_at_str,
        version=chat.version,
    )
    return HTMLResponse(content=html_content)
