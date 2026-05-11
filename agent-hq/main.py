# -*- coding: utf-8 -*-
import sys
import os
import json
import sqlite3
import asyncio
from pathlib import Path
from datetime import datetime
from typing import AsyncGenerator

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
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
    """Load knowledge files relevant to a brand."""
    context_parts = []
    brand_dir = KNOWLEDGE_DIR / brand_id
    global_dir = KNOWLEDGE_DIR

    for search_dir in [global_dir, brand_dir]:
        if search_dir.exists():
            for f in sorted(search_dir.glob("*.txt"))[:5]:
                try:
                    text = f.read_text(encoding="utf-8")
                    context_parts.append(f"=== {f.name} ===\n{text[:3000]}")
                except Exception:
                    pass
            for f in sorted(search_dir.glob("*.md"))[:3]:
                try:
                    text = f.read_text(encoding="utf-8")
                    context_parts.append(f"=== {f.name} ===\n{text[:3000]}")
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
            system_prompt = "You are a helpful AI assistant in testing mode. You have no memory of previous conversations."
            history = []
        else:
            brand_name = next((b["name"] for b in BRANDS if b["id"] == brand_id), brand_id)
            knowledge = get_knowledge_context(brand_id)
            system_prompt = f"""Du er Director — en intelligent AI-assistent for {brand_name}.
Du hjælper med marketing, content, strategi og analyse.
Du svarer altid på dansk med mindre andet anmodes.

Vidénsbase:\n{knowledge if knowledge else 'Ingen vidensbase uploadet endnu.'}"""
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
                safe_chunk = text_chunk.replace("\n", "\\n")
                payload = json.dumps({"text": text_chunk}, ensure_ascii=False)
                yield f"data: {payload}\n\n"

        if not testing_mode:
            save_message(brand_id, "user", message)
            save_message(brand_id, "assistant", full_response)

        yield "data: [DONE]\n\n"

    except Exception as e:
        error_msg = json.dumps({"error": str(e)}, ensure_ascii=False)
        yield f"data: {error_msg}\n\n"


@app.post("/chat")
async def chat(request: ChatRequest):
    return StreamingResponse(
        stream_claude_response(request.brand_id, request.message, request.testing_mode),
        media_type="text/event-stream; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        }
    )


@app.get("/history/{brand_id}")
async def get_history(brand_id: str):
    history = get_chat_history(brand_id, limit=50)
    return {"messages": history}


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
    if KNOWLEDGE_DIR.exists():
        for f in sorted(KNOWLEDGE_DIR.rglob("*")):
            if f.is_file() and f.suffix in (".txt", ".md", ".json"):
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
  .card p, .card .value { font-size: 0.8rem; color: #888; }
  input[type=text], input[type=url] { background: #1e1e2e; border: 1px solid #2a2a3a; color: #e0e0e0; padding: 10px 14px; border-radius: 8px; font-size: 0.875rem; width: 100%; outline: none; }
  input[type=text]:focus, input[type=url]:focus { border-color: #6c63ff; }
  .btn { background: #6c63ff; color: #fff; border: none; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-size: 0.875rem; font-weight: 600; }
  .btn:hover { background: #5a52e0; }
  .btn-danger { background: #ff4444; }
  .btn-danger:hover { background: #cc3333; }
  .url-list { margin-top: 12px; }
  .url-item { background: #13131c; border: 1px solid #2a2a3a; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; font-size: 0.8rem; }
  .url-item .url-text { color: #9d96ff; word-break: break-all; }
  .url-item .url-meta { color: #555; margin-top: 4px; }
  .status-badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 0.7rem; }
  .status-pending { background: #ff990022; color: #ff9900; border: 1px solid #ff990044; }
  .status-done { background: #00cc6622; color: #00cc66; border: 1px solid #00cc6644; }
  .file-item { background: #13131c; border: 1px solid #2a2a3a; border-radius: 8px; padding: 10px 14px; margin-bottom: 8px; font-size: 0.8rem; }
  .file-name { color: #9d96ff; }
  .file-meta { color: #555; font-size: 0.72rem; margin-top: 2px; }
  .testing-banner { background: #ff4444; color: white; text-align: center; padding: 8px; font-size: 0.8rem; font-weight: 600; letter-spacing: 0.05em; }
  .clear-btn { background: none; border: 1px solid #2a2a3a; color: #666; padding: 6px 14px; border-radius: 6px; cursor: pointer; font-size: 0.75rem; }
  .clear-btn:hover { border-color: #ff4444; color: #ff4444; }
  .header-actions { margin-left: auto; display: flex; gap: 8px; align-items: center; }
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
    <div class="nav-item" data-tab="knowledge" onclick="switchTab(this)">
      &#128218; Vidensbase
    </div>
    <div class="nav-item" data-tab="urls" onclick="switchTab(this)">
      &#127909; YouTube URLs
    </div>
  </nav>
  <div class="main">

    <!-- Brand Chat -->
    <div class="tab-content active" id="tab-chat-jens-christian-health">
      <div class="chat-header">
        <h2>Jens Christian Health &mdash; Director</h2>
        <div class="header-actions">
          <button class="clear-btn" onclick="clearHistory('jens-christian-health')">Ryd chat</button>
        </div>
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

    <!-- Testing Room -->
    <div class="tab-content" id="tab-chat-testing">
      <div class="testing-banner">TESTING RUM &mdash; Ingen hukommelse &mdash; Ingen systemkontekst</div>
      <div class="chat-header">
        <h2>Testing Room</h2>
        <div class="header-actions">
          <button class="clear-btn" onclick="clearMessages('testing')">Ryd visning</button>
        </div>
      </div>
      <div class="chat-messages" id="messages-testing"></div>
      <div class="chat-input-area">
        <div class="typing-indicator" id="typing-testing">
          <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
          <span style="font-size:0.78rem;color:#555">Svarer...</span>
        </div>
        <div class="chat-input-row">
          <textarea id="input-testing" placeholder="Test uden hukommelse eller kontekst..." rows="1" onkeydown="handleKey(event,'testing')"></textarea>
          <button class="send-btn" id="send-testing" onclick="sendMessage('testing')">Send</button>
        </div>
      </div>
    </div>

    <!-- Knowledge Base -->
    <div class="tab-content" id="tab-knowledge">
      <div class="panel">
        <h2>&#128218; Vidensbase</h2>
        <div class="card">
          <h3>Filer p&#229; serveren</h3>
          <p style="margin-bottom:12px">Filer ligger i <code style="color:#9d96ff">/root/knowledge/</code> &mdash; upload via scp fra din Mac:</p>
          <code style="color:#888;font-size:0.8rem">scp din-fil.txt root@187.124.17.73:/root/knowledge/</code>
        </div>
        <div id="knowledge-files" class="url-list"></div>
      </div>
    </div>

    <!-- YouTube URLs -->
    <div class="tab-content" id="tab-urls">
      <div class="panel">
        <h2>&#127909; YouTube URLs</h2>
        <div class="card">
          <h3>Tilf&#248;j ny URL</h3>
          <div style="display:flex;gap:10px;margin-top:8px">
            <input type="url" id="new-url" placeholder="https://www.youtube.com/watch?v=..." />
            <button class="btn" onclick="addUrl()">Tilf&#248;j</button>
          </div>
          <p style="margin-top:8px;font-size:0.75rem;color:#555">URLs behandles p&#229; din Mac med batch.py og synkroniseres automatisk.</p>
        </div>
        <div id="url-list" class="url-list"></div>
      </div>
    </div>

  </div>
</div>

<script>
const localHistory = {};

function switchTab(el) {
  document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
  el.classList.add('active');
  const tabId = 'tab-' + el.dataset.tab;
  document.getElementById(tabId).classList.add('active');
  if (el.dataset.tab === 'knowledge') loadKnowledge();
  if (el.dataset.tab === 'urls') loadUrls();
  if (el.dataset.tab.startsWith('chat-') && el.dataset.tab !== 'chat-testing') {
    const brandId = el.dataset.tab.replace('chat-', '');
    loadHistory(brandId);
  }
}

function formatTime() {
  return new Date().toLocaleTimeString('da-DK', {hour:'2-digit',minute:'2-digit'});
}

function appendMessage(brandId, role, content) {
  const container = document.getElementById('messages-' + brandId);
  const div = document.createElement('div');
  div.className = 'message ' + role;
  div.innerHTML = `
    <div class="message-bubble">${escapeHtml(content)}</div>
    <div class="message-meta">${role === 'user' ? 'Dig' : 'Director'} &bull; ${formatTime()}</div>
  `;
  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function escapeHtml(text) {
  return text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

async function loadHistory(brandId) {
  const res = await fetch('/history/' + brandId);
  const data = await res.json();
  const container = document.getElementById('messages-' + brandId);
  container.innerHTML = '';
  data.messages.forEach(m => appendMessage(brandId, m.role, m.content));
}

async function clearHistory(brandId) {
  if (!confirm('Ryd al chathistorik for denne brand?')) return;
  await fetch('/history/' + brandId, {method:'DELETE'});
  document.getElementById('messages-' + brandId).innerHTML = '';
}

function clearMessages(brandId) {
  document.getElementById('messages-' + brandId).innerHTML = '';
}

async function sendMessage(brandId) {
  const input = document.getElementById('input-' + brandId);
  const sendBtn = document.getElementById('send-' + brandId);
  const message = input.value.trim();
  if (!message) return;

  input.value = '';
  input.style.height = 'auto';
  sendBtn.disabled = true;

  appendMessage(brandId, 'user', message);

  const typingEl = document.getElementById('typing-' + brandId);
  typingEl.classList.add('visible');

  const container = document.getElementById('messages-' + brandId);
  const assistantDiv = document.createElement('div');
  assistantDiv.className = 'message assistant';
  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = '';
  const meta = document.createElement('div');
  meta.className = 'message-meta';
  meta.textContent = 'Director • ' + formatTime();
  assistantDiv.appendChild(bubble);
  assistantDiv.appendChild(meta);
  container.appendChild(assistantDiv);

  const isTestingMode = brandId === 'testing';

  try {
    const response = await fetch('/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({brand_id: brandId, message: message, testing_mode: isTestingMode})
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder('utf-8');
    let buffer = '';
    let fullText = '';

    typingEl.classList.remove('visible');

    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, {stream: true});
      const lines = buffer.split('\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const payload = line.slice(6);
          if (payload === '[DONE]') break;
          try {
            const parsed = JSON.parse(payload);
            if (parsed.text) {
              fullText += parsed.text;
              bubble.textContent = fullText;
              container.scrollTop = container.scrollHeight;
            }
          } catch(e) {}
        }
      }
    }
  } catch(e) {
    bubble.textContent = 'Fejl: ' + e.message;
    typingEl.classList.remove('visible');
  }

  sendBtn.disabled = false;
  input.focus();
}

function handleKey(e, brandId) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage(brandId);
  }
  const ta = e.target;
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
}

async function addUrl() {
  const urlInput = document.getElementById('new-url');
  const url = urlInput.value.trim();
  if (!url) return;
  await fetch('/urls', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({url: url})
  });
  urlInput.value = '';
  loadUrls();
}

async function loadUrls() {
  const res = await fetch('/urls');
  const data = await res.json();
  const list = document.getElementById('url-list');
  if (!data.urls.length) {
    list.innerHTML = '<div style="color:#555;font-size:0.8rem">Ingen URLs tilføjet endnu.</div>';
    return;
  }
  list.innerHTML = data.urls.map(u => `
    <div class="url-item">
      <div class="url-text">${escapeHtml(u.url)}</div>
      <div class="url-meta">${u.title || 'Ingen titel'} &bull; <span class="status-badge status-${u.status}">${u.status}</span></div>
    </div>
  `).join('');
}

async function loadKnowledge() {
  const res = await fetch('/knowledge');
  const data = await res.json();
  const list = document.getElementById('knowledge-files');
  if (!data.files.length) {
    list.innerHTML = '<div style="color:#555;font-size:0.8rem">Ingen filer fundet i /root/knowledge/</div>';
    return;
  }
  list.innerHTML = data.files.map(f => `
    <div class="file-item">
      <div class="file-name">${escapeHtml(f.name)}</div>
      <div class="file-meta">${f.path} &bull; ${(f.size/1024).toFixed(1)} KB &bull; ${f.modified.slice(0,16)}</div>
    </div>
  `).join('');
}

loadHistory('jens-christian-health');
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
