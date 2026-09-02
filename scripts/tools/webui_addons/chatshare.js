/**
 * AI Lab — ChatShare Client-Side Cloud Publisher & Structured Extractor (Zero LLM Tokens)
 * Extrae el 100% de los mensajes desde IndexedDB / DOM preservando:
 *  - role (user, assistant, system)
 *  - reasoning_content / thinking (cadena de pensamiento)
 *  - content (respuesta final limpia)
 *  - tool_calls / multimedia
 * Y publica directamente a ai.castelancarpinteyro.com con QR y enlace público.
 */

(function () {
  'use strict';

  // 1. Conector a la API de ChatShare (Nube prioritaria con fallback local)
  async function postToChatShare(endpoint, data) {
    const apis = [
      'https://ai.castelancarpinteyro.com/api/v1',
      'http://localhost:9095/api/v1'
    ];
    let lastErr = null;
    for (const base of apis) {
      try {
        const resp = await fetch(`${base}${endpoint}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data)
        });
        if (resp.ok) {
          return await resp.json();
        }
      } catch (err) {
        lastErr = err;
      }
    }
    throw lastErr || new Error('No se pudo conectar con el backend de ChatShare');
  }

  // 2. Extractor de Máxima Fidelidad (IndexedDB + Svelte Store + DOM inteligente)
  async function extractFullConversation() {
    let messages = await extractFromIndexedDB();
    if (messages && messages.length > 0) {
      return messages;
    }

    messages = extractFromLocalStorage();
    if (messages && messages.length > 0) {
      return messages;
    }

    return extractFromDOM();
  }

  // A. Extractor IndexedDB (Dexie / Svelte IDB de llama.cpp)
  async function extractFromIndexedDB() {
    try {
      if (!window.indexedDB) return null;
      let dbs = [];
      if (indexedDB.databases) {
        dbs = await indexedDB.databases();
      } else {
        dbs = [{ name: 'conversations' }, { name: 'chat' }, { name: 'llama' }, { name: 'webui' }];
      }

      for (const dbInfo of dbs) {
        if (!dbInfo.name) continue;
        const msgs = await new Promise((resolve) => {
          const req = indexedDB.open(dbInfo.name);
          req.onerror = () => resolve(null);
          req.onsuccess = (e) => {
            const db = e.target.result;
            const storeNames = Array.from(db.objectStoreNames);
            if (!storeNames.includes('messages') && !storeNames.includes('conversations')) {
              db.close();
              return resolve(null);
            }

            try {
              const tx = db.transaction(storeNames, 'readonly');
              let activeConvId = null;

              // Obtener la conversación más reciente
              if (storeNames.includes('conversations')) {
                const convStore = tx.objectStore('conversations');
                const convReq = convStore.getAll();
                convReq.onsuccess = () => {
                  const convs = convReq.result || [];
                  if (convs.length > 0) {
                    convs.sort((a, b) => (b.lastModified || b.timestamp || 0) - (a.lastModified || a.timestamp || 0));
                    activeConvId = convs[0].id;
                  }
                };
              }

              if (storeNames.includes('messages')) {
                const msgStore = tx.objectStore('messages');
                const msgReq = msgStore.getAll();
                msgReq.onsuccess = () => {
                  const allMsgs = msgReq.result || [];
                  let filtered = allMsgs;
                  if (activeConvId) {
                    const convMsgs = allMsgs.filter(m => m.convId === activeConvId || m.conversationId === activeConvId);
                    if (convMsgs.length > 0) filtered = convMsgs;
                  }
                  
                  // Ordenar cronológicamente
                  filtered.sort((a, b) => (a.timestamp || 0) - (b.timestamp || 0));

                  const structured = filtered.map(m => {
                    const thinking = m.reasoning_content || m.thinking || m.thought || null;
                    let content = m.content || m.text || '';
                    if (typeof content !== 'string') content = JSON.stringify(content);
                    
                    // Si el pensamiento está dentro del texto con tags <thought>
                    if (!thinking && typeof content === 'string') {
                      const match = content.match(/<(thought|thinking)>([\s\S]*?)<\/\1>/i);
                      if (match) {
                        return {
                          role: m.role || 'assistant',
                          content: content.replace(match[0], '').trim(),
                          thinking: match[2].trim(),
                          tool_calls: m.tool_calls || m.tools || null
                        };
                      }
                    }

                    return {
                      role: m.role || 'assistant',
                      content: content.trim(),
                      thinking: thinking ? thinking.trim() : null,
                      tool_calls: m.tool_calls || m.tools || null
                    };
                  }).filter(m => m.content || m.thinking);

                  db.close();
                  resolve(structured.length > 0 ? structured : null);
                };
                msgReq.onerror = () => { db.close(); resolve(null); };
              } else {
                db.close();
                resolve(null);
              }
            } catch (err) {
              db.close();
              resolve(null);
            }
          };
        });

        if (msgs && msgs.length > 0) {
          return msgs;
        }
      }
    } catch (e) {
      console.warn('[ChatShare] IndexedDB error:', e);
    }
    return null;
  }

  // B. Extractor LocalStorage
  function extractFromLocalStorage() {
    try {
      for (let i = 0; i < localStorage.length; i++) {
        const key = localStorage.key(i);
        if (key && (key.includes('chat') || key.includes('history') || key.includes('messages') || key.includes('conversation'))) {
          const raw = localStorage.getItem(key);
          if (!raw) continue;
          try {
            const data = JSON.parse(raw);
            let items = null;
            if (Array.isArray(data)) items = data;
            else if (data && Array.isArray(data.messages)) items = data.messages;
            else if (data && typeof data === 'object') {
              const vals = Object.values(data).filter(v => v && (v.role || v.content));
              if (vals.length > 0) items = vals;
            }

            if (items && items.length > 0) {
              return items.map(m => {
                let thinking = m.reasoning_content || m.thinking || m.thought || null;
                let content = typeof m.content === 'string' ? m.content : (m.text || JSON.stringify(m.content || ''));
                if (!thinking && typeof content === 'string') {
                  const match = content.match(/<(thought|thinking)>([\s\S]*?)<\/\1>/i);
                  if (match) {
                    thinking = match[2].trim();
                    content = content.replace(match[0], '').trim();
                  }
                }
                return {
                  role: m.role || 'assistant',
                  content: content.trim(),
                  thinking: thinking ? thinking.trim() : null,
                  tool_calls: m.tool_calls || null
                };
              }).filter(m => m.content || m.thinking);
            }
          } catch(e) {}
        }
      }
    } catch (e) {}
    return null;
  }

  // C. Extractor DOM Inteligente con Separación de Pensamiento y Código
  function extractFromDOM() {
    const msgs = [];
    const chatContainers = document.querySelectorAll('[data-role], .chat-message, [class*="message-container"], [class*="chat-item"], div[class*="message"]');
    
    if (chatContainers.length > 0) {
      chatContainers.forEach(container => {
        const isUser = container.getAttribute('data-role') === 'user' ||
                       container.classList.contains('user') ||
                       container.querySelector('[class*="user"]') !== null;
        const role = isUser ? 'user' : 'assistant';

        // Detectar bloque de pensamiento/razonamiento dentro del contenedor
        let thinking = null;
        const thoughtNode = container.querySelector('[class*="thought"], [class*="thinking"], details, [data-thought]');
        if (thoughtNode) {
          thinking = thoughtNode.innerText.trim();
        }

        // Clonar nodo para extraer solo el texto de respuesta sin el pensamiento
        const clone = container.cloneNode(true);
        const cloneThoughts = clone.querySelectorAll('[class*="thought"], [class*="thinking"], details, [data-thought], [class*="avatar"]');
        cloneThoughts.forEach(n => n.remove());

        let content = clone.innerText.trim();
        
        // Limpiar tags de pensamiento si existieran en el texto
        if (typeof content === 'string') {
          const match = content.match(/<(thought|thinking)>([\s\S]*?)<\/\1>/i);
          if (match) {
            if (!thinking) thinking = match[2].trim();
            content = content.replace(match[0], '').trim();
          }
        }

        if (content || thinking) {
          msgs.push({
            role: role,
            content: content || '',
            thinking: thinking || null
          });
        }
      });
    }

    if (msgs.length === 0) {
      document.querySelectorAll('main p, div[class*="prose"] p').forEach((p, idx) => {
        const t = p.innerText.trim();
        if (t && t.length > 2) {
          msgs.push({
            role: idx % 2 === 0 ? 'user' : 'assistant',
            content: t,
            thinking: null
          });
        }
      });
    }

    return msgs;
  }

  // 3. Inyección de Interfaz UI
  function attachButton() {
    if (document.getElementById('chatshare-btn')) return;
    if (!document.body) return;

    if (!document.getElementById('chatshare-styles')) {
      const style = document.createElement('style');
      style.id = 'chatshare-styles';
      style.textContent = `
        #chatshare-btn {
          position: fixed !important;
          top: 10px !important;
          right: 75px !important;
          z-index: 2147483647 !important;
          background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 100%) !important;
          color: #ffffff !important;
          border: 1px solid rgba(255, 255, 255, 0.35) !important;
          border-radius: 8px !important;
          padding: 6px 14px !important;
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
          font-size: 13px !important;
          font-weight: 600 !important;
          display: inline-flex !important;
          align-items: center !important;
          gap: 6px !important;
          cursor: pointer !important;
          box-shadow: 0 4px 14px rgba(0, 0, 0, 0.45) !important;
          pointer-events: auto !important;
          visibility: visible !important;
          opacity: 1 !important;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1) !important;
        }
        #chatshare-btn:hover {
          transform: translateY(-1px) scale(1.02) !important;
          box-shadow: 0 6px 20px rgba(124, 58, 237, 0.5) !important;
          filter: brightness(1.12) !important;
        }
        #chatshare-modal-overlay {
          display: none;
          position: fixed;
          inset: 0;
          background: rgba(0, 0, 0, 0.78);
          backdrop-filter: blur(8px);
          z-index: 2147483647;
          align-items: center;
          justify-content: center;
        }
        #chatshare-modal-overlay.active { display: flex !important; }
        #chatshare-modal {
          background: #18181b;
          color: #f4f4f5;
          border: 1px solid #27272a;
          border-radius: 16px;
          width: 92%;
          max-width: 560px;
          padding: 24px;
          box-shadow: 0 25px 50px rgba(0, 0, 0, 0.85);
          font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          animation: chatsharePop 0.22s cubic-bezier(0.16, 1, 0.3, 1);
        }
        @keyframes chatsharePop {
          from { transform: scale(0.93); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }
        .cs-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          padding-bottom: 12px;
          border-bottom: 1px solid #27272a;
        }
        .cs-title { font-size: 17px; font-weight: 700; display: flex; align-items: center; gap: 8px; }
        .cs-badge {
          background: rgba(16, 185, 129, 0.18);
          color: #34d399;
          font-size: 11px;
          padding: 3px 8px;
          border-radius: 9999px;
          font-weight: 600;
          border: 1px solid rgba(16, 185, 129, 0.35);
        }
        .cs-close { background: transparent; border: none; color: #a1a1aa; font-size: 24px; cursor: pointer; line-height: 1; }
        .cs-close:hover { color: #ffffff; }
        .cs-card {
          background: #09090b;
          border: 1px solid #27272a;
          border-radius: 12px;
          padding: 16px;
          text-align: center;
          margin-bottom: 16px;
        }
        .cs-qr-container {
          background: #ffffff;
          padding: 10px;
          border-radius: 10px;
          display: inline-block;
          margin: 10px auto 12px auto;
          box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }
        .cs-qr-container img { display: block; width: 190px; height: 190px; }
        .cs-link-box { display: flex; gap: 8px; margin-top: 8px; }
        .cs-link-input {
          flex: 1;
          background: #18181b;
          border: 1px solid #3f3f46;
          color: #38bdf8;
          padding: 8px 12px;
          border-radius: 8px;
          font-size: 12.5px;
          font-family: monospace;
          outline: none;
        }
        .cs-copy-btn {
          background: #4f46e5;
          color: #ffffff;
          border: none;
          border-radius: 8px;
          padding: 8px 14px;
          font-weight: 600;
          font-size: 12.5px;
          cursor: pointer;
          transition: background 0.15s ease;
          display: flex;
          align-items: center;
          gap: 4px;
        }
        .cs-copy-btn:hover { background: #4338ca; }
        .cs-secondary-options {
          display: grid;
          grid-template-columns: 1fr 1fr 1fr;
          gap: 8px;
        }
        .cs-sec-btn {
          background: #27272a;
          border: 1px solid #3f3f46;
          color: #d4d4d8;
          padding: 8px 10px;
          border-radius: 8px;
          cursor: pointer;
          font-size: 11.5px;
          font-weight: 500;
          text-align: center;
          transition: all 0.15s ease;
        }
        .cs-sec-btn:hover { background: #3f3f46; border-color: #8b5cf6; color: #fff; }
        .cs-toast {
          position: fixed; bottom: 24px; right: 24px; background: #10b981; color: #fff;
          padding: 10px 18px; border-radius: 8px; font-size: 13.5px; font-weight: 600;
          z-index: 2147483647; display: none; box-shadow: 0 10px 25px rgba(0,0,0,0.4);
        }
        .cs-loading {
          padding: 30px;
          text-align: center;
          color: #a1a1aa;
          font-size: 14px;
        }
        .cs-spinner {
          width: 32px;
          height: 32px;
          border: 3px solid rgba(139, 92, 246, 0.2);
          border-top-color: #8b5cf6;
          border-radius: 50%;
          animation: csSpin 0.7s linear infinite;
          margin: 0 auto 12px auto;
        }
        @keyframes csSpin { to { transform: rotate(360deg); } }
      `;
      document.head.appendChild(style);
    }

    const btn = document.createElement('button');
    btn.id = 'chatshare-btn';
    btn.innerHTML = `
      <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor">
        <path d="M18 16.08c-.76 0-1.44.3-1.96.77L8.91 12.7c.05-.23.09-.46.09-.7s-.04-.47-.09-.7l7.05-4.11c.54.5 1.25.81 2.04.81 1.66 0 3-1.34 3-3s-1.34-3-3-3-3 1.34-3 3c0 .24.04.47.09.7L8.04 9.81C7.5 9.31 6.79 9 6 9c-1.66 0-3 1.34-3 3s1.34 3 3 3c.79 0 1.5-.31 2.04-.81l7.12 4.16c-.05.21-.08.43-.08.65 0 1.61 1.31 2.92 2.92 2.92s2.92-1.31 2.92-2.92c0-1.61-1.31-2.92-2.92-2.92z"/>
      </svg>
      Compartir Chat (ChatShare)
    `;
    btn.onclick = handleShareWorkflow;
    document.body.appendChild(btn);

    if (!document.getElementById('chatshare-modal-overlay')) {
      const overlay = document.createElement('div');
      overlay.id = 'chatshare-modal-overlay';
      overlay.innerHTML = `
        <div id="chatshare-modal">
          <div class="cs-header">
            <div class="cs-title">
              <span>🌐 Compartir en ai.castelancarpinteyro.com</span>
              <span class="cs-badge">⚡ 0 Tokens</span>
            </div>
            <button class="cs-close" id="cs-close-btn">&times;</button>
          </div>
          <div id="cs-modal-body"></div>
        </div>
      `;
      document.body.appendChild(overlay);

      document.getElementById('cs-close-btn').onclick = () => overlay.classList.remove('active');
      overlay.onclick = (e) => { if (e.target === overlay) overlay.classList.remove('active'); };
    }
  }

  function showToast(msg) {
    let t = document.getElementById('chatshare-toast');
    if (!t) {
      t = document.createElement('div');
      t.id = 'chatshare-toast';
      t.className = 'cs-toast';
      document.body.appendChild(t);
    }
    t.textContent = msg;
    t.style.display = 'block';
    setTimeout(() => { t.style.display = 'none'; }, 3000);
  }

  async function handleShareWorkflow() {
    const overlay = document.getElementById('chatshare-modal-overlay');
    const body = document.getElementById('cs-modal-body');
    overlay.classList.add('active');

    body.innerHTML = `
      <div class="cs-loading">
        <div class="cs-spinner"></div>
        <p><b>Extrayendo mensajes y razonamiento...</b></p>
        <p style="font-size:12px;opacity:0.7;">Analizando base de datos local y conectando con ai.castelancarpinteyro.com</p>
      </div>
    `;

    const msgs = await extractFullConversation();
    if (!msgs || msgs.length === 0) {
      body.innerHTML = `
        <div style="text-align:center;padding:24px;color:#a1a1aa;">
          <p style="font-size:15px;margin-bottom:8px;">⚠️ No se detectaron mensajes en el chat activo.</p>
          <p style="font-size:12.5px;">Escribe una consulta en la interfaz de Gemma 4 y vuelve a presionar el botón.</p>
        </div>
      `;
      return;
    }

    try {
      const thoughtsCount = msgs.filter(m => m.thinking).length;
      const title = `Conversación AI Lab (${msgs.length} mensajes • ${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})})`;
      
      // A. Crear Chat en la API de ChatShare
      const createData = await postToChatShare('/chats', {
        title: title,
        messages: msgs,
        metadata: {
          source: "webui_zero_token",
          model: "gemma-4-12b-it",
          thoughts_included: thoughtsCount > 0,
          total_messages: msgs.length
        }
      });
      const chatId = createData.id;

      // B. Generar Enlace Público
      const shareData = await postToChatShare(`/chats/${chatId}/share`, {
        expires_hours: 72,
        label: "Compartido desde WebUI"
      });
      const publicUrl = shareData.url;

      // C. Copiar automáticamente al portapapeles
      try {
        await navigator.clipboard.writeText(publicUrl);
        showToast('🔗 ¡Enlace público copiado al portapapeles!');
      } catch (err) {
        showToast('✅ ¡Chat publicado con éxito!');
      }

      // D. Código QR visual interactivo
      const encodedUrl = encodeURIComponent(publicUrl);
      const qrUrl = `https://api.qrserver.com/v1/create-qr-code/?size=200x200&margin=8&data=${encodedUrl}`;

      // E. Renderizar resultado
      body.innerHTML = `
        <div class="cs-card">
          <div style="font-size:12.5px;color:#34d399;margin-bottom:4px;font-weight:600;">
            ✓ ${msgs.length} mensajes extraídos (${thoughtsCount} bloques de razonamiento preservados)
          </div>
          <div style="font-size:13px;color:#a1a1aa;margin-bottom:6px;">📱 <b>Escanea para abrir en tu celular o compartir:</b></div>
          <div class="cs-qr-container">
            <img src="${qrUrl}" alt="Código QR ChatShare" loading="lazy" />
          </div>
          
          <div style="font-size:12px;color:#a1a1aa;margin-bottom:6px;text-align:left;">🌐 <b>Enlace Público (Válido por 72 horas):</b></div>
          <div class="cs-link-box">
            <input type="text" readonly class="cs-link-input" id="cs-target-url" value="${publicUrl}" />
            <button class="cs-copy-btn" id="cs-copy-link-btn">📋 Copiar</button>
          </div>
        </div>

        <div style="font-size:11.5px;color:#71717a;margin-bottom:8px;text-align:center;">
          Otras opciones de respaldo local:
        </div>
        <div class="cs-secondary-options">
          <button class="cs-sec-btn" id="cs-sec-html">🌐 Descargar HTML</button>
          <button class="cs-sec-btn" id="cs-sec-md">📝 Copiar Markdown</button>
          <button class="cs-sec-btn" id="cs-sec-json">📋 Copiar JSON</button>
        </div>
      `;

      document.getElementById('cs-copy-link-btn').onclick = () => {
        navigator.clipboard.writeText(publicUrl);
        showToast('🔗 Enlace copiado al portapapeles');
      };

      document.getElementById('cs-sec-html').onclick = () => {
        const chatHtml = msgs.map(m => `
          <div style="margin-bottom:20px;${m.role==='user'?'text-align:right;':''}">
            <div style="display:inline-block;max-width:85%;text-align:left;padding:12px 16px;border-radius:12px;background:${m.role==='user'?'#4f46e5':'#18181b'};border:1px solid #27272a;color:#fff;">
              <div style="font-size:11px;font-weight:700;opacity:0.7;margin-bottom:4px;">${m.role==='user'?'👤 Tú':'🤖 Gemma 4 12B IT'}</div>
              ${m.thinking ? `<details style="margin-bottom:8px;padding:8px;background:rgba(124,58,237,0.15);border:1px solid rgba(124,58,237,0.3);border-radius:8px;font-size:12px;font-family:monospace;color:#c084fc;"><summary style="cursor:pointer;font-weight:bold;">🧠 Razonamiento / Pensamiento</summary><pre style="white-space:pre-wrap;margin-top:6px;">${m.thinking.replace(/</g,'&lt;').replace(/>/g,'&gt;')}</pre></details>` : ''}
              <div>${m.content.replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/\n/g,'<br>')}</div>
            </div>
          </div>
        `).join('');
        const fullHtml = `<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><title>ChatShare — Conversación AI Lab</title><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>body{font-family:system-ui,-apple-system,sans-serif;background:#09090b;color:#f4f4f5;margin:0;padding:20px;display:flex;justify-content:center;}.container{max-width:760px;width:100%;margin-top:20px;}.header{text-align:center;border-bottom:1px solid #27272a;padding-bottom:16px;margin-bottom:24px;}.header h1{font-size:22px;margin:0 0 6px 0;color:#a78bfa;}.header p{font-size:13px;color:#a1a1aa;margin:0;}</style></head><body><div class="container"><div class="header"><h1>💬 Conversación Respaldada (ChatShare)</h1><p>Generada sin consumo de tokens • ${new Date().toLocaleString()}</p></div><div>${chatHtml}</div></div></body></html>`;
        const blob = new Blob([fullHtml], { type: 'text/html;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `chatshare_${Date.now()}.html`;
        a.click();
        showToast('📥 Archivo HTML descargado');
      };

      document.getElementById('cs-sec-md').onclick = () => {
        let md = `# ${title}\n*Fecha: ${new Date().toLocaleString()}* | *Enlace Público: ${publicUrl}*\n\n---\n\n`;
        msgs.forEach(m => {
          md += `${m.role === 'user' ? '👤 **Usuario**' : '🤖 **Asistente (Gemma 4)**'}:\n\n`;
          if (m.thinking) {
            md += `> 🧠 **Razonamiento:**\n> ${m.thinking.replace(/\n/g, '\n> ')}\n\n`;
          }
          md += `${m.content}\n\n---\n\n`;
        });
        navigator.clipboard.writeText(md);
        showToast('✅ Markdown limpio copiado');
      };

      document.getElementById('cs-sec-json').onclick = () => {
        navigator.clipboard.writeText(JSON.stringify({
          title: title,
          url: publicUrl,
          created_at: new Date().toISOString(),
          model: "Gemma 4 12B IT (Local :9090)",
          conversations: msgs.map(m => ({
            from: m.role === 'user' ? 'human' : 'gpt',
            value: m.content,
            thinking: m.thinking || undefined
          }))
        }, null, 2));
        showToast('✅ JSON copiado al portapapeles');
      };

    } catch (err) {
      body.innerHTML = `
        <div style="padding:20px;color:#f87171;text-align:center;">
          <p style="font-weight:700;font-size:15px;margin-bottom:8px;">❌ Error al conectar con ChatShare</p>
          <p style="font-size:12.5px;color:#a1a1aa;margin-bottom:14px;">${err.message}</p>
        </div>
      `;
    }
  }

  setInterval(attachButton, 600);
  window.addEventListener('load', attachButton);
  document.addEventListener('DOMContentLoaded', attachButton);
})();
