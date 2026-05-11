# -*- coding: utf-8 -*-
import os
import json
import sqlite3
from pathlib import Path
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

DB_PATH = "/root/agent-hq/agent_hq.db"
KNOWLEDGE_DIR = Path("/root/knowledge")
KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

BRANDS = [
    {"id": "jens-christian-health", "name": "Jens Christian Health"},
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS youtube_urls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            url TEXT NOT NULL UNIQUE,
            title TEXT,
            status TEXT DEFAULT 'pending',
            brand_id TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


init_db()


def get_knowledge_context(brand_id: str) -> str:
    context_parts = []
    for agent_dir in sorted(KNOWLEDGE_DIR.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
            continue
        for sub_dir in sorted(agent_dir.iterdir()):
            if not sub_dir.is_dir():
                continue
            knowledge_dir = sub_dir / "_knowledge"
            if not knowledge_dir.exists():
                continue
            for f in sorted(knowledge_dir.glob("*.md"), reverse=True)[:3]:
                try:
                    text = f.read_text(encoding="utf-8")
                    label = f"{agent_dir.name}/{sub_dir.name}/{f.name}"
                    context_parts.append(f"=== {label} ===\n{text[:4000]}")
                except Exception:
                    pass
    for f in sorted(KNOWLEDGE_DIR.glob("*.md"))[:5]:
        try:
            context_parts.append(f"=== {f.name} ===\n{f.read_text(encoding='utf-8')[:3000]}")
        except Exception:
            pass
    return "\n\n".join(context_parts)


def get_chat_history(brand_id: str, limit: int = 20) -> list:
    conn = get_db()
    rows = conn.execute(
        "SELECT role, content FROM messages WHERE brand_id = ? ORDER BY id DESC LIMIT ?",
        (brand_id, limit)
    ).fetchall()
    conn.close()
    return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def save_message(brand_id: str, role: str, content: str):
    conn = get_db()
    conn.execute(
        "INSERT INTO messages (brand_id, role, content) VALUES (?, ?, ?)",
        (brand_id, role, content)
    )
    conn.commit()
    conn.close()


class ChatRequest(BaseModel):
    brand_id: str
    message: str
    testing_mode: bool = False


class UrlRequest(BaseModel):
    url: str
    brand_id: str = ""
    title: str = ""


async def stream_claude_response(brand_id: str, message: str, testing_mode: bool) -> AsyncGenerator[str, None]:
    try:
        if testing_mode:
            system_prompt = "You are a helpful AI assistant in testing mode."
            history = []
        else:
            brand_name = next((b["name"] for b in BRANDS if b["id"] == brand_id), brand_id)
            knowledge = get_knowledge_context(brand_id)
            system_prompt = f"""Du er Director — en intelligent AI-assistent for {brand_name}.
Du hjælper med marketing, content, strategi og analyse baseret på din vidensbase.
Du svarer altid på dansk med mindre andet anmodes.

Vidensbase:\n{knowledge if knowledge else 'Ingen knowledge-filer fundet endnu.'}"""
            history = get_chat_history(brand_id)
        history.append({"role": "user", "content": message})
        full_response = ""
        with client.messages.stream(
            model="claude-opus-4-7",
            max_tokens=2048,
            system=system_prompt,
            messages=history,
        ) as stream:
            for text_chunk in stream.text_stream:
                full_response += text_chunk
                payload = json.dumps({"text": text_chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
        if not testing_mode:
            save_message(brand_id, "user", message)
            save_message(brand_id, "assistant", full_response)
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"


@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        stream_claude_response(request.brand_id, request.message, request.testing_mode),
        media_type="text/event-stream; charset=utf-8",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    )


@app.get("/history/{brand_id}")
async def get_history(brand_id: str):
    return {"messages": get_chat_history(brand_id, limit=50)}


@app.delete("/history/{brand_id}")
async def clear_history(brand_id: str):
    conn = get_db()
    conn.execute("DELETE FROM messages WHERE brand_id = ?", (brand_id,))
    conn.commit()
    conn.close()
    return {"status": "cleared"}


@app.get("/brands")
async def get_brands():
    return {"brands": BRANDS}


@app.post("/urls")
async def add_url(request: UrlRequest):
    conn = get_db()
    try:
        conn.execute(
            "INSERT OR IGNORE INTO youtube_urls (url, title, brand_id) VALUES (?, ?, ?)",
            (request.url, request.title, request.brand_id)
        )
        conn.commit()
        return {"status": "added"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    finally:
        conn.close()


@app.get("/urls")
async def list_urls():
    conn = get_db()
    rows = conn.execute("SELECT * FROM youtube_urls ORDER BY id DESC").fetchall()
    conn.close()
    return {"urls": [dict(r) for r in rows]}


@app.get("/knowledge")
async def list_knowledge():
    files = []
    for f in sorted(KNOWLEDGE_DIR.rglob("*.md")):
        if f.is_file():
            files.append({
                "name": f.name,
                "path": str(f.relative_to(KNOWLEDGE_DIR)),
                "size": f.stat().st_size,
                "modified": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })
    return {"files": files}


HTML = """
<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Mallmedia Agent HQ</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', system-ui, sans-serif; background: #0f0f13; color: #e0e0e0; height: 100vh; display: flex; flex-direction: column; }
  header { background: #1a1a24; border-bottom: 1px solid #2a2a3a; padding: 14px 24px; display: flex; align-items: center; gap: 16px; }
  header h1 { font-size: 1.1rem; font-weight: 600; color: #fff; letter-spacing: 0.05em; }
  header .badge { background: #6c63ff22; color: #9d96ff; border: 1px solid #6c63ff44; padding: 3px 10px; border-radius: 20px; font-size: 0.75rem; }
  .layout { display: flex; flex: 1; overflow: hidden; }
  .sidebar { width: 220px; background: #13131c; border-right: 1px solid #2a2a3a; display: flex; flex-direction: column; padding: 16px 0; }
  .sidebar-section { padding: 8px 16px 4px; font-size: 0.65rem; text-transform: uppercase; letter-spacing: 0.1em; color: #555; }
  .nav-item { padding: 9px 20px; cursor: pointer; font-size: 0.875rem; color: #888; display: flex; align-items: center; gap: 10px; transition: all 0.15s; }
  .nav-item:hover { background: #1e1e2e; color: #ccc; }
  .nav-item.active { background: #6c63ff22; color: #9d96ff; border-right: 2px solid #6c63ff; }
  .nav-item .dot { width: 8px; height: 8px; border-radius: 50%; background: #6c63ff; }
  .nav-item .dot.testing { background: #ff6b6b; }
  .main { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  .tab-content { display: none; flex: 1; flex-direction: column; overflow: hidden; }
  .tab-content.active { display: flex; }
  .chat-messages { flex: 1; overflow-y: auto; padding: 24px; display: flex; flex-direction: column; gap: 16px; }
  .message { max-width: 780px; }
  .message.user { align-self: flex-end; }
  .message.assistant { align-self: flex-start; }
  .message-bubble { padding: 12px 16px; border-radius: 12px; line-height: 1.6; font-size: 0.9rem; white-space: pre-wrap; word-wrap: break-word; }
  .user .message-bubble { background: #6c63ff; color: #fff; border-bottom-right-radius: 4px; }
  .assistant .message-bubble { background: #1e1e2e; color: #e0e0e0; border-bottom-left-radius: 4px; border: 1px solid #2a2a3a; }
  .message-meta { font-size: 0.7rem; color: #555; margin-top: 4px; padding: 0 4px; }
  .user .message-meta { text-align: right; }
  .chat-input-area { padding: 16px 24px; border-top: 1px solid #2a2a3a; background: #13131c; }
  .chat-input-row { display: flex; gap: 10px; align-items: flex-end; }
  .chat-input-row textarea { flex: 1; background: #1e1e2e; border: 1px solid #2a2a3a; color: #e0e0e0; padding: 12px 16px; border-radius: 10px; resize: none; font-family: inherit; font-size: 0.9rem; min-height: 48px; max-height: 160px; outline: none; transition: border-color 0.15s; }
  .chat-input-row textarea:focus { border-color: #6c63ff; }
  .send-btn { background: #6c63ff; color: #fff; border: none; padding: 12px 20px; border-radius: 10px; cursor: pointer; font-size: 0.9rem; font-weight: 600; transition: background 0.15s; white-space: nowrap; }
  .send-btn:hover { background: #5a52e0; }
  .send-btn:disabled { background: #333; color: #666; cursor: not-allowed; }
  .panel { flex: 1; overflow-y: auto; padding: 24px; }
  .panel h2 { font-size: 1rem; font-weight: 600; color: #fff; margin-bottom: 16px; }
  .card { background: #1e1e2e; border: 1px solid #2a2a3a; border-radius: 10px; padding: 16px; margin-bottom: 12px; }
  .card h3 { font-size: 0.875rem; color: #ccc; margin-bottom: 8px; }
  .card p { font-size: 0.8rem; color: #888; }
  code { background: #13131c; padding: 2px 6px; border-radius: 4px; font-family: monospace; font-size: 0.8rem; }
  input[type=url] { background: #1e1e2e; border: 1px solid #2a2a3a; color: #e0e0e0; padding: 10px 14px; border-radius: 8px; font-size: 0.875rem; width: 100%; outline: none; }
  input[type=url]:focus { border-color: #6c63ff; }
  .btn { background: #6c63ff; color: #fff; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-size: 0.875rem; font-weight: 600; }
  .btn:hover { background: #5a52e0; }
  .url-list { margin-top: 12px; }
  .url-item, .file-item { background: #13131c; border: 1px solid #2a2a3a; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; font-size: 0.8rem; }
  .url-text, .file-name { color: #9d96ff; word-break: break-all; }
  .url-meta, .file-meta { color: #555; font-size: 0.72rem; margin-top: 4px; }
  .status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; }
  .status-pending { background: #ff990022; color: #ff9900; border: 1px solid #ff990044; }
  .status-done { background: #00cc6622; color: #00cc66; border: 1px solid #00cc6644; }
  .testing-banner { background: #c0392b; color: white; text-align: center; padding: 8px; font-size: 0.8rem; font-weight: 600; }
  .clear-btn { background: none; border: 1px solid #2a2a3a; color: #666; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; }
  .clear-btn:hover { border-color: #ff4444; color: #ff4444; }
  .header-actions { margin-left: auto; }
  .chat-header { padding: 12px 24px; border-bottom: 1px solid #2a2a3a; background: #13131c; display: flex; align-items: center; gap: 12px; }
  .chat-header h2 { font-size: 0.95rem; color: #ccc; }
  .typing-indicator { display: none; align-items: center; gap: 6px; padding: 8px 0; }
  .typing-indicator.visible { display: flex; }
  .typing-dot { width: 6px; height: 6px; border-radius: 50%; background: #6c63ff; animation: pulse 1.2s infinite; }
  .typing-dot:nth-child(2) { animation-delay: 0.2s; }
  .typing-dot:nth-child(3) { animation-delay: 0.4s; }
  @keyframes pulse { 0%, 80%, 100% { opacity: 0.3; } 40% { opacity: 1; } }
  ::-webkit-scrollbar { width: 6px; } ::-webkit-scrollbar-track { background: transparent; } ::-webkit-scrollbar-thumb { background: #2a2a3a; border-radius: 3px; }
</style>
</head>
<body>
<header>
  <h1>&#9679; MALLMEDIA AGENT HQ</h1>
  <span class="badge">Director v1.0</span>
</header>
<div class="layout">
  <nav class="sidebar">
    <div class="sidebar-section">Brands</div>
    <div class="nav-item active" data-tab="chat-jens-christian-health" onclick="switchTab(this)">
      <span class="dot"></span> Jens Christian Health
    </div>
    <div class="sidebar-section" style="margin-top:16px">Rum</div>
    <div class="nav-item" data-tab="chat-testing" onclick="switchTab(this)">
      <span class="dot testing"></span> Testing
    </div>
    <div class="sidebar-section" style="margin-top:16px">System</div>
    <div class="nav-item" data-tab="knowledge" onclick="switchTab(this)">&#128218; Vidensbase</div>
    <div class="nav-item" data-tab="urls" onclick="switchTab(this)">&#127909; YouTube URLs</div>
  </nav>
  <div class="main">
    <div class="tab-content active" id="tab-chat-jens-christian-health">
      <div class="chat-header">
        <h2>Jens Christian Health &mdash; Director</h2>
        <div class="header-actions"><button class="clear-btn" onclick="clearHistory('jens-christian-health')">Ryd chat</button></div>
      </div>
      <div class="chat-messages" id="messages-jens-christian-health"></div>
      <div class="chat-input-area">
        <div class="typing-indicator" id="typing-jens-christian-health">
          <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
          <span style="font-size:0.78rem;color:#555">Director skriver...</span>
        </div>
        <div class="chat-input-row">
          <textarea id="input-jens-christian-health" placeholder="Skriv til Director..." rows="1" onkeydown="handleKey(event,'jens-christian-health')"></textarea>
          <button class="send-btn" id="send-jens-christian-health" onclick="sendMessage('jens-christian-health')">Send</button>
        </div>
      </div>
    </div>
    <div class="tab-content" id="tab-chat-testing">
      <div class="testing-banner">TESTING RUM &mdash; Ingen hukommelse &mdash; Ingen systemkontekst</div>
      <div class="chat-header">
        <h2>Testing Room</h2>
        <div class="header-actions"><button class="clear-btn" onclick="clearMessages('testing')">Ryd visning</button></div>
      </div>
      <div class="chat-messages" id="messages-testing"></div>
      <div class="chat-input-area">
        <div class="typing-indicator" id="typing-testing">
          <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
          <span style="font-size:0.78rem;color:#555">Svarer...</span>
        </div>
        <div class="chat-input-row">
          <textarea id="input-testing" placeholder="Test uden hukommelse..." rows="1" onkeydown="handleKey(event,'testing')"></textarea>
          <button class="send-btn" id="send-testing" onclick="sendMessage('testing')">Send</button>
        </div>
      </div>
    </div>
    <div class="tab-content" id="tab-knowledge">
      <div class="panel">
        <h2>&#128218; Vidensbase</h2>
        <div class="card">
          <h3>Synkroniser fra Mac</h3>
          <p style="margin-bottom:8px">K&#248;r <code>batch.py</code> p&#229; din Mac, derefter:</p>
          <code style="display:block;padding:10px;margin-top:6px">rsync -avz -e "ssh -i ~/.ssh/id_ed25519" ~/Main\ Claude/ecom-agents/ root@187.124.17.73:/root/knowledge/</code>
        </div>
        <div id="knowledge-files"><div style="color:#555;font-size:0.8rem">Indl&#230;ser...</div></div>
      </div>
    </div>
    <div class="tab-content" id="tab-urls">
      <div class="panel">
        <h2>&#127909; YouTube URLs</h2>
        <div class="card">
          <h3>Tilf&#248;j ny URL</h3>
          <div style="display:flex;gap:10px;margin-top:8px">
            <input type="url" id="new-url" placeholder="https://www.youtube.com/watch?v=..." />
            <button class="btn" onclick="addUrl()">Tilf&#248;j</button>
          </div>
        </div>
        <div id="url-list" class="url-list"></div>
      </div>
    </div>
  </div>
</div>
<script>
function switchTab(el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  document.getElementById('tab-' + el.dataset.tab).classList.add('active');
  if (el.dataset.tab === 'knowledge') loadKnowledge();
  if (el.dataset.tab === 'urls') loadUrls();
  if (el.dataset.tab.startsWith('chat-') && el.dataset.tab !== 'chat-testing') loadHistory(el.dataset.tab.replace('chat-', ''));
}
function escapeHtml(t) { return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function formatTime() { return new Date().toLocaleTimeString('da-DK',{hour:'2-digit',minute:'2-digit'}); }
function appendMessage(brandId, role, content) {
  const c = document.getElementById('messages-' + brandId);
  const d = document.createElement('div');
  d.className = 'message ' + role;
  d.innerHTML = `<div class="message-bubble">${escapeHtml(content)}</div><div class="message-meta">${role==='user'?'Dig':'Director'} &bull; ${formatTime()}</div>`;
  c.appendChild(d); c.scrollTop = c.scrollHeight; return d;
}
async function loadHistory(id) {
  const d = await (await fetch('/history/'+id)).json();
  const c = document.getElementById('messages-'+id); c.innerHTML='';
  d.messages.forEach(m => appendMessage(id, m.role, m.content));
}
async function clearHistory(id) {
  if(!confirm('Ryd chathistorik?')) return;
  await fetch('/history/'+id,{method:'DELETE'});
  document.getElementById('messages-'+id).innerHTML='';
}
function clearMessages(id) { document.getElementById('messages-'+id).innerHTML=''; }
async function sendMessage(brandId) {
  const input = document.getElementById('input-'+brandId);
  const btn = document.getElementById('send-'+brandId);
  const msg = input.value.trim(); if(!msg) return;
  input.value=''; input.style.height='auto'; btn.disabled=true;
  appendMessage(brandId,'user',msg);
  const typing = document.getElementById('typing-'+brandId);
  typing.classList.add('visible');
  const c = document.getElementById('messages-'+brandId);
  const ad = document.createElement('div'); ad.className='message assistant';
  const bubble = document.createElement('div'); bubble.className='message-bubble';
  const meta = document.createElement('div'); meta.className='message-meta'; meta.textContent='Director • '+formatTime();
  ad.appendChild(bubble); ad.appendChild(meta); c.appendChild(ad);
  try {
    const res = await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({brand_id:brandId,message:msg,testing_mode:brandId==='testing'})});
    typing.classList.remove('visible');
    const reader = res.body.getReader(); const dec = new TextDecoder('utf-8');
    let buf='',full='';
    while(true) {
      const {done,value}=await reader.read(); if(done) break;
      buf+=dec.decode(value,{stream:true});
      const lines=buf.split('\n'); buf=lines.pop();
      for(const line of lines) {
        if(!line.startsWith('data: ')) continue;
        const p=line.slice(6); if(p==='[DONE]') break;
        try { const j=JSON.parse(p); if(j.text){full+=j.text;bubble.textContent=full;c.scrollTop=c.scrollHeight;} } catch(e){}
      }
    }
  } catch(e) { bubble.textContent='Fejl: '+e.message; typing.classList.remove('visible'); }
  btn.disabled=false; input.focus();
}
function handleKey(e,id) {
  if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();sendMessage(id);}
  e.target.style.height='auto'; e.target.style.height=Math.min(e.target.scrollHeight,160)+'px';
}
async function addUrl() {
  const i=document.getElementById('new-url'); const url=i.value.trim(); if(!url) return;
  await fetch('/urls',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
  i.value=''; loadUrls();
}
async function loadUrls() {
  const d=await(await fetch('/urls')).json();
  const l=document.getElementById('url-list');
  l.innerHTML=d.urls.length?d.urls.map(u=>`<div class="url-item"><div class="url-text">${escapeHtml(u.url)}</div><div class="url-meta">${u.title||'Ingen titel'} &bull; <span class="status-badge status-${u.status}">${u.status}</span></div></div>`).join(''):'<div style="color:#555;font-size:0.8rem">Ingen URLs endnu.</div>';
}
async function loadKnowledge() {
  const d=await(await fetch('/knowledge')).json();
  const l=document.getElementById('knowledge-files');
  l.innerHTML=d.files.length?d.files.map(f=>`<div class="file-item"><div class="file-name">${escapeHtml(f.name)}</div><div class="file-meta">${escapeHtml(f.path)} &bull; ${(f.size/1024).toFixed(1)} KB</div></div>`).join(''):'<div style="color:#555;font-size:0.8rem">Ingen filer. Sync fra Mac først.</div>';
}
loadHistory('jens-christian-health'); loadKnowledge();
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(content=HTML, media_type="text/html; charset=utf-8")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
