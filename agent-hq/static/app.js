'use strict';

// ── API ───────────────────────────────────────────────────────────────────────
const API = {
  async _f(method, path, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) { opts.headers['Content-Type'] = 'application/json'; opts.body = JSON.stringify(body); }
    const res = await fetch(path, opts);
    if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
    return method === 'DELETE' ? null : res.json();
  },
  get:    (p)    => API._f('GET',    p),
  post:   (p, b) => API._f('POST',   p, b),
  patch:  (p, b) => API._f('PATCH',  p, b),
  delete: (p)    => API._f('DELETE', p),
};

// ── State ─────────────────────────────────────────────────────────────────────
const S = {
  view: 'testing',
  brandSlug: null,
  agentName: null,
  brands: [],
  brandAgents: {},
  expanded: new Set(),
  testMessages: [],
  rendering: false,
  pendingRender: false,
  apiKeySet: true,
  kbPendingCount: 0,
};

// ── Helpers ───────────────────────────────────────────────────────────────────
const dot  = (s) => `<span class="dot dot--${s}"></span>`;
const esc  = (s) => String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
const trunc = (s, n) => s && s.length > n ? s.slice(0, n) + '…' : (s || '');

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso.endsWith('Z') ? iso : iso + 'Z');
  return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
       + ', ' + d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });
}

function agentBadge(s) {
  const m = { idle: 'Idle', working: 'Working', waiting_approval: 'Awaiting Approval' };
  return `<span class="badge badge--agent-${s}">${m[s] ?? s}</span>`;
}
function reportBadge(s) {
  const m = { pending: 'Pending', approved: 'Approved', rejected: 'Rejected' };
  return `<span class="badge badge--report-${s}">${m[s] ?? s}</span>`;
}
function taskBadge(s) {
  const m = { pending: 'Pending', in_progress: 'In Progress', completed: 'Completed', failed: 'Failed' };
  return `<span class="badge badge--task-${s}">${m[s] ?? s}</span>`;
}

function renderMarkdown(text) {
  let s = esc(text);
  s = s.replace(/```[\w]*\n?([\s\S]*?)```/g, (_, code) =>
    `<pre><code>${code.trim()}</code></pre>`);
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*([^*]+)\*/g,     '<em>$1</em>');
  s = s.replace(/^### (.+)$/gm, '<h4>$1</h4>');
  s = s.replace(/^## (.+)$/gm,  '<h3>$1</h3>');
  s = s.replace(/((?:^[ \t]*[-•] .+\n?)+)/gm, (block) => {
    const items = block.trim().split('\n').map(l => `<li>${l.replace(/^[ \t]*[-•] /,'')}</li>`).join('');
    return `<ul>${items}</ul>`;
  });
  s = s.replace(/\n\n+/g, '</p><p>');
  s = s.replace(/\n/g, '<br>');
  return `<p>${s}</p>`;
}

// ── Streaming ─────────────────────────────────────────────────────────────────
async function streamChat({ url, body, onToken, onDone, onError }) {
  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch (e) { onError(e.message); return; }

  const reader  = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      const raw = line.slice(6).trim();
      if (raw === '[DONE]') { onDone(); return; }
      try {
        const obj = JSON.parse(raw);
        if (obj.error)  { onError(obj.error); return; }
        if (obj.text)    onToken(obj.text);
      } catch (_) {}
    }
  }
  onDone();
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
async function loadSidebar() {
  const brands = await API.get('/api/brands');
  S.brands = brands;
  for (const b of brands) {
    const agents = await API.get(`/api/brands/${b.id}/agents`);
    S.brandAgents[b.slug] = agents;
    if (!S.expanded.has(b.slug)) S.expanded.add(b.slug);
  }
  renderSidebar();
}

function renderSidebar() {
  const nav = document.getElementById('sidebar-nav');
  if (!nav) return;

  let html = `
    <div class="nav-section">Workspace</div>
    <a class="nav-link ${S.view === 'testing' ? 'nav-link--active' : ''}"
       href="#testing" data-nav="testing">
      <span>🧪</span><span>Testing</span>
    </a>
    <a class="nav-link ${S.view === 'knowledge' ? 'nav-link--active' : ''}"
       href="#knowledge" data-nav="knowledge">
      <span>📚</span><span>Knowledge Base</span>
      ${S.kbPendingCount > 0 ? `<span class="queue-badge">${S.kbPendingCount}</span>` : ''}
    </a>`;

  html += `<div class="nav-section" style="display:flex;align-items:center;justify-content:space-between">
    <span>Brands</span>
    <a href="#new-brand" style="color:var(--accent);font-size:18px;line-height:1;text-decoration:none" title="New brand">+</a>
  </div>`;

  for (const b of S.brands) {
    const open    = S.expanded.has(b.slug);
    const agents  = S.brandAgents[b.slug] || [];
    const isOvAct = S.view === 'brand-overview' && S.brandSlug === b.slug;

    html += `
    <div class="nav-brand-toggle" data-brand-toggle="${b.slug}">
      <span>📁</span>
      <span>${esc(b.name)}</span>
      <span class="nav-brand-chevron ${open ? 'open' : ''}">▶</span>
    </div>
    <div class="nav-brand-children ${open ? 'open' : ''}" id="brand-children-${b.slug}">
      <a class="nav-link nav-link-sub ${isOvAct ? 'nav-link--active' : ''}"
         href="#brand/${b.slug}" data-nav="brand-overview" data-slug="${b.slug}">
        Overview
      </a>
      ${agents.map(a => {
        const isAct = S.view === 'agent-chat' && S.brandSlug === b.slug && S.agentName === a.name;
        return `<a class="nav-link nav-link-sub ${isAct ? 'nav-link--active' : ''}"
                   href="#brand/${b.slug}/${a.name}"
                   data-nav="agent-chat" data-slug="${b.slug}" data-agent="${a.name}">
          ${dot(a.status)}<span>${esc(a.display_name)}</span>
        </a>`;
      }).join('')}
    </div>`;
  }

  nav.innerHTML = html;

  nav.querySelectorAll('[data-brand-toggle]').forEach(el => {
    el.onclick = () => {
      const slug = el.dataset.brandToggle;
      if (S.expanded.has(slug)) S.expanded.delete(slug);
      else S.expanded.add(slug);
      renderSidebar();
    };
  });
}

// ── Router ────────────────────────────────────────────────────────────────────
window.addEventListener('hashchange', route);

function route() {
  const h = window.location.hash.slice(1) || 'testing';

  if (h === 'testing') {
    S.view = 'testing'; S.brandSlug = null; S.agentName = null;
  } else if (h === 'knowledge') {
    S.view = 'knowledge'; S.brandSlug = null; S.agentName = null;
  } else if (h === 'new-brand') {
    S.view = 'new-brand'; S.brandSlug = null; S.agentName = null;
  } else if (h.startsWith('brand/')) {
    const parts = h.slice(6).split('/');
    if (parts.length >= 2) {
      S.view = 'agent-chat'; S.brandSlug = parts[0]; S.agentName = parts[1];
    } else {
      S.view = 'brand-overview'; S.brandSlug = parts[0]; S.agentName = null;
    }
  } else {
    S.view = 'testing'; S.brandSlug = null; S.agentName = null;
  }

  renderSidebar();
  render();
}

// ── Main render ───────────────────────────────────────────────────────────────
async function render() {
  if (S.rendering) { S.pendingRender = true; return; }
  S.rendering = true; S.pendingRender = false;
  try {
    const app = document.getElementById('app');
    app.innerHTML = '<div class="loader">Loading…</div>';

    if (S.view === 'testing')             await mountTesting(app);
    else if (S.view === 'knowledge')      await mountKnowledge(app);
    else if (S.view === 'brand-overview') await mountBrandOverview(app);
    else if (S.view === 'agent-chat')     await mountAgentChat(app);
    else if (S.view === 'new-brand')      await mountNewBrand(app);
  } catch (e) {
    document.getElementById('app').innerHTML =
      `<div class="page-body"><div style="color:var(--red);padding:24px">Error: ${esc(e.message)}</div></div>`;
  } finally {
    S.rendering = false;
    if (S.pendingRender) render();
  }
}

// ── View: New Brand ───────────────────────────────────────────────────────────
async function mountNewBrand(app) {
  app.innerHTML = `
<div class="page-body">
  <div class="page-header">
    <div>
      <h1 class="page-title">Nyt Brand</h1>
      <p class="page-sub">Opret et nyt workspace — du får 4 agenter automatisk</p>
    </div>
  </div>
  <div class="panel">
    <div class="panel-header"><h2 class="panel-title">Brand Info</h2></div>
    <div class="kb-form" style="padding:16px">
      <div class="kb-form-group">
        <label class="kb-form-label">Brand navn</label>
        <input class="kb-input" id="new-brand-name" placeholder="fx. Min Webshop">
      </div>
      <div class="kb-form-group">
        <label class="kb-form-label">Kontekst — beskriv produktet, målgruppe, pris og kanaler</label>
        <textarea class="kb-input" id="new-brand-context" rows="7"
          placeholder="Produkt: ...\nPris: ...\nMålgruppe: ...\nKanaler: Meta, TikTok, ...\nPlatform: Shopify"></textarea>
      </div>
      <button class="btn btn--primary" id="create-brand-btn">Opret Brand</button>
    </div>
  </div>
</div>`;

  document.getElementById('create-brand-btn').addEventListener('click', async () => {
    const name    = document.getElementById('new-brand-name').value.trim();
    const context = document.getElementById('new-brand-context').value.trim();
    if (!name) { alert('Brand navn er påkrævet'); return; }
    const btn = document.getElementById('create-brand-btn');
    btn.disabled = true;
    try {
      const res = await API.post('/api/brands', { name, context });
      await loadSidebar();
      window.location.hash = `#brand/${res.slug}`;
    } catch (e) {
      alert('Fejl: ' + e.message);
      btn.disabled = false;
    }
  });
}

// ── View: Testing Room ────────────────────────────────────────────────────────
async function mountTesting(app) {
  const config = await API.get('/api/config');
  S.apiKeySet = config.api_key_set;

  app.innerHTML = `
<div class="chat-wrapper">
  <div class="sandbox-bar">
    <span>🧪</span>
    <span><strong>Sandbox</strong> — intet herfra påvirker dine brands. Ingen historik gemmes.</span>
    <button class="btn btn--ghost btn--sm" style="margin-left:auto" id="test-clear-btn">New conversation</button>
  </div>
  ${!S.apiKeySet ? `
  <div class="api-key-warning">
    <strong>API key not configured.</strong> Set the <code>ANTHROPIC_API_KEY</code> environment variable
    and restart the server to enable the chat interface.
  </div>` : ''}
  <div class="messages" id="test-messages">
    <div class="chat-empty">
      <div class="chat-empty-icon">🧪</div>
      <div class="chat-empty-title">Testing Sandbox</div>
      <div class="chat-empty-sub">
        Sparringspartner med adgang til din vidensbase. Ingen historik gemmes.
      </div>
    </div>
  </div>
  <div class="chat-input-bar">
    <textarea class="chat-input" id="test-input" placeholder="Send a message…" rows="1"
      ${!S.apiKeySet ? 'disabled' : ''}></textarea>
    <button class="chat-send-btn" id="test-send-btn" ${!S.apiKeySet ? 'disabled' : ''}>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
        <path d="M15.964.686a.5.5 0 0 0-.65-.65L.767 5.855H.766l-.452.18a.5.5 0 0 0-.082.887l.41.26.001.002 4.995 3.178 3.178 4.995.002.002.26.41a.5.5 0 0 0 .886-.083l6-15Zm-1.833 1.89L6.637 10.07l-.215-.338a.5.5 0 0 0-.154-.154l-.338-.215 7.494-7.494 1.178-.471-.47 1.178Z"/>
      </svg>
    </button>
  </div>
</div>`;

  renderTestMessages();

  const input = document.getElementById('test-input');
  if (input) {
    input.addEventListener('input', () => autoResize(input));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendTestMessage(); }
    });
  }

  document.getElementById('test-send-btn')?.addEventListener('click', sendTestMessage);
  document.getElementById('test-clear-btn')?.addEventListener('click', () => {
    S.testMessages = [];
    renderTestMessages();
  });
}

function renderTestMessages() {
  const container = document.getElementById('test-messages');
  if (!container) return;
  if (S.testMessages.length === 0) {
    container.innerHTML = `
      <div class="chat-empty">
        <div class="chat-empty-icon">🧪</div>
        <div class="chat-empty-title">Testing Sandbox</div>
        <div class="chat-empty-sub">Sparringspartner med adgang til din vidensbase. Ingen historik gemmes.</div>
      </div>`;
    return;
  }
  container.innerHTML = S.testMessages.map(m => messageBubble(m.role, m.content)).join('');
  container.scrollTop = container.scrollHeight;
}

async function sendTestMessage() {
  const input = document.getElementById('test-input');
  const sendBtn = document.getElementById('test-send-btn');
  if (!input || !sendBtn) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = ''; autoResize(input);
  input.disabled = true; sendBtn.disabled = true;

  S.testMessages.push({ role: 'user', content: text });

  const container = document.getElementById('test-messages');
  if (container) {
    container.innerHTML = S.testMessages.map(m => messageBubble(m.role, m.content)).join('');
    const typing = document.createElement('div');
    typing.className = 'message message--assistant';
    typing.id = 'typing-msg';
    typing.innerHTML = `
      <div class="message-sender">Claude</div>
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>`;
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
  }

  let accumulated = '';

  await streamChat({
    url: '/api/chat/test',
    body: { messages: S.testMessages },
    onToken(t) {
      accumulated += t;
      const typingEl = document.getElementById('typing-msg');
      if (typingEl) {
        typingEl.innerHTML = `
          <div class="message-sender">Claude</div>
          <div class="message-bubble">${renderMarkdown(accumulated)}</div>`;
      }
      if (container) container.scrollTop = container.scrollHeight;
    },
    onDone() {
      if (accumulated) S.testMessages.push({ role: 'assistant', content: accumulated });
      renderTestMessages();
      input.disabled = false; sendBtn.disabled = false;
      input.focus();
    },
    onError(err) {
      const typingEl = document.getElementById('typing-msg');
      if (typingEl) typingEl.remove();
      if (container) {
        const errEl = document.createElement('div');
        errEl.style.cssText = 'color:var(--red);font-size:12px;padding:8px 20px';
        errEl.textContent = `Error: ${err}`;
        container.appendChild(errEl);
      }
      S.testMessages.pop();
      input.disabled = false; sendBtn.disabled = false;
    },
  });
}

// ── View: Brand Overview ──────────────────────────────────────────────────────
async function mountBrandOverview(app) {
  const brand = S.brands.find(b => b.slug === S.brandSlug);
  if (!brand) { app.innerHTML = `<div class="page-body"><div class="error">Brand not found</div></div>`; return; }

  const [stats, agents, queue] = await Promise.all([
    API.get(`/api/brands/${brand.id}/stats`),
    API.get(`/api/brands/${brand.id}/agents`),
    API.get(`/api/brands/${brand.id}/queue`),
  ]);

  S.brandAgents[brand.slug] = agents;

  app.innerHTML = `
<div class="page-body">
  <div class="page-header">
    <div>
      <h1 class="page-title">${esc(brand.name)}</h1>
      <p class="page-sub">Brand workspace</p>
    </div>
    <button class="btn btn--ghost btn--sm" id="edit-brand-toggle">⚙ Indstillinger</button>
  </div>

  <div id="brand-edit-panel" style="display:none">
    <div class="panel" style="border:1px solid var(--accent);margin-bottom:16px">
      <div class="panel-header"><h2 class="panel-title">Brand Indstillinger</h2></div>
      <div class="kb-form" style="padding:16px">
        <div class="kb-form-group">
          <label class="kb-form-label">Brand navn</label>
          <input class="kb-input" id="edit-brand-name" value="${esc(brand.name)}">
        </div>
        <div class="kb-form-group">
          <label class="kb-form-label">Kontekst — produkt, målgruppe, pris, kanaler</label>
          <textarea class="kb-input" id="edit-brand-context" rows="7">${esc(brand.context || '')}</textarea>
        </div>
        <div style="display:flex;gap:8px;align-items:center">
          <button class="btn btn--primary" id="save-brand-btn">Gem</button>
          <button class="btn btn--ghost btn--sm" id="cancel-edit-btn">Annuller</button>
          <button class="btn btn--danger btn--sm" id="delete-brand-btn" style="margin-left:auto">Slet brand</button>
        </div>
      </div>
    </div>
  </div>

  <div class="stat-row">
    <div class="stat-card">
      <div class="stat-val">${stats.active_agents}</div>
      <div class="stat-lbl">Active Agents</div>
    </div>
    <div class="stat-card stat-card--warn">
      <div class="stat-val">${stats.pending_approvals}</div>
      <div class="stat-lbl">Pending Approvals</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">${stats.active_tasks}</div>
      <div class="stat-lbl">Active Tasks</div>
    </div>
    <div class="stat-card">
      <div class="stat-val">${stats.completed_tasks}</div>
      <div class="stat-lbl">Completed Tasks</div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2 class="panel-title">Agents</h2>
    </div>
    <div class="agent-status-grid">
      ${agents.map(a => `
        <a class="agent-status-card" href="#brand/${brand.slug}/${a.name}">
          <div class="asc-top">${dot(a.status)}<span class="asc-name">${esc(a.display_name)}</span></div>
          ${agentBadge(a.status)}
        </a>
      `).join('')}
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2 class="panel-title">
        Approval Queue
        ${queue.length > 0 ? `<span class="count">${queue.length}</span>` : ''}
      </h2>
    </div>
    ${queue.length === 0
      ? `<div class="empty"><span class="empty-icon">✓</span><span>No pending approvals</span></div>`
      : queue.map(r => queueCard(r)).join('')
    }
  </div>
</div>`;

  // Edit toggle
  document.getElementById('edit-brand-toggle').addEventListener('click', () => {
    const panel = document.getElementById('brand-edit-panel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
  });
  document.getElementById('cancel-edit-btn').addEventListener('click', () => {
    document.getElementById('brand-edit-panel').style.display = 'none';
  });

  // Save brand
  document.getElementById('save-brand-btn').addEventListener('click', async () => {
    const name    = document.getElementById('edit-brand-name').value.trim();
    const context = document.getElementById('edit-brand-context').value.trim();
    if (!name) { alert('Brand navn er påkrævet'); return; }
    const btn = document.getElementById('save-brand-btn');
    btn.disabled = true;
    try {
      const res = await API.patch(`/api/brands/${brand.id}`, { name, context });
      await loadSidebar();
      if (res.slug !== brand.slug) {
        window.location.hash = `#brand/${res.slug}`;
      } else {
        S.brandSlug = res.slug;
        mountBrandOverview(app);
      }
    } catch (e) {
      alert('Fejl: ' + e.message);
      btn.disabled = false;
    }
  });

  // Delete brand
  document.getElementById('delete-brand-btn').addEventListener('click', async () => {
    if (!confirm(`Slet "${brand.name}" og alt tilhørende data?`)) return;
    await API.delete(`/api/brands/${brand.id}`);
    await loadSidebar();
    window.location.hash = '#testing';
  });

  // Approve / reject
  app.querySelectorAll('[data-approve]').forEach(btn => {
    btn.onclick = async () => {
      btn.disabled = true;
      await API.patch(`/api/reports/${btn.dataset.approve}`, { status: 'approved' });
      mountBrandOverview(app);
    };
  });
  app.querySelectorAll('[data-reject]').forEach(btn => {
    btn.onclick = async () => {
      btn.disabled = true;
      await API.patch(`/api/reports/${btn.dataset.reject}`, { status: 'rejected' });
      mountBrandOverview(app);
    };
  });
}

// ── View: Agent Chat ──────────────────────────────────────────────────────────
async function mountAgentChat(app) {
  const brand = S.brands.find(b => b.slug === S.brandSlug);
  if (!brand) { app.innerHTML = `<div class="page-body"><div class="error">Brand not found</div></div>`; return; }

  const agents = S.brandAgents[brand.slug] || await API.get(`/api/brands/${brand.id}/agents`);
  const agent  = agents.find(a => a.name === S.agentName);
  if (!agent) { app.innerHTML = `<div class="page-body"><div class="error">Agent not found</div></div>`; return; }

  const [config, history] = await Promise.all([
    API.get('/api/config'),
    API.get(`/api/brands/${brand.id}/agents/${agent.id}/messages`),
  ]);
  S.apiKeySet = config.api_key_set;

  app.innerHTML = `
<div class="chat-wrapper">
  <div class="chat-header">
    <div class="chat-header-info">
      <div class="chat-header-name">${dot(agent.status)} ${esc(agent.display_name)}</div>
      <div class="chat-header-sub">${esc(brand.name)} · ${agentBadge(agent.status)}</div>
    </div>
    <div class="chat-header-controls">
      <select class="select" id="agent-status-sel" data-id="${agent.id}">
        <option value="idle"             ${agent.status === 'idle'             ? 'selected' : ''}>Idle</option>
        <option value="working"          ${agent.status === 'working'          ? 'selected' : ''}>Working</option>
        <option value="waiting_approval" ${agent.status === 'waiting_approval' ? 'selected' : ''}>Awaiting Approval</option>
      </select>
      <button class="btn btn--ghost btn--sm" id="clear-history-btn">Clear history</button>
    </div>
  </div>
  ${!S.apiKeySet ? `
  <div class="api-key-warning" style="margin:16px">
    <strong>API key not configured.</strong> Set <code>ANTHROPIC_API_KEY</code> and restart.
  </div>` : ''}
  <div class="messages" id="agent-messages">
    ${history.length === 0
      ? `<div class="chat-empty">
          <div class="chat-empty-icon">💬</div>
          <div class="chat-empty-title">Start a conversation</div>
          <div class="chat-empty-sub">
            ${esc(agent.display_name)} er klar. Samtaler gemmes per agent.
          </div>
        </div>`
      : history.map(m => messageBubble(m.role, m.content)).join('')
    }
  </div>
  <div class="chat-input-bar">
    <textarea class="chat-input" id="agent-input"
      placeholder="Message ${esc(agent.display_name)}…" rows="1"
      ${!S.apiKeySet ? 'disabled' : ''}></textarea>
    <button class="chat-send-btn" id="agent-send-btn" ${!S.apiKeySet ? 'disabled' : ''}>
      <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
        <path d="M15.964.686a.5.5 0 0 0-.65-.65L.767 5.855H.766l-.452.18a.5.5 0 0 0-.082.887l.41.26.001.002 4.995 3.178 3.178 4.995.002.002.26.41a.5.5 0 0 0 .886-.083l6-15Zm-1.833 1.89L6.637 10.07l-.215-.338a.5.5 0 0 0-.154-.154l-.338-.215 7.494-7.494 1.178-.471-.47 1.178Z"/>
      </svg>
    </button>
  </div>
</div>`;

  const container = document.getElementById('agent-messages');
  if (container) container.scrollTop = container.scrollHeight;

  const input = document.getElementById('agent-input');
  if (input) {
    input.addEventListener('input', () => autoResize(input));
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendAgentMessage(brand, agent); }
    });
  }

  document.getElementById('agent-send-btn')?.addEventListener('click',
    () => sendAgentMessage(brand, agent));

  document.getElementById('clear-history-btn')?.addEventListener('click', async () => {
    if (!confirm('Clear all chat history for this agent?')) return;
    await API.delete(`/api/brands/${brand.id}/agents/${agent.id}/messages`);
    mountAgentChat(app);
  });

  document.getElementById('agent-status-sel')?.addEventListener('change', async (e) => {
    await API.patch(`/api/agents/${agent.id}`, { status: e.target.value });
    agent.status = e.target.value;
    renderSidebar();
  });
}

async function sendAgentMessage(brand, agent) {
  const input   = document.getElementById('agent-input');
  const sendBtn = document.getElementById('agent-send-btn');
  if (!input || !sendBtn) return;
  const text = input.value.trim();
  if (!text) return;

  input.value = ''; autoResize(input);
  input.disabled = true; sendBtn.disabled = true;

  const container = document.getElementById('agent-messages');

  const emptyEl = container?.querySelector('.chat-empty');
  if (emptyEl) emptyEl.remove();

  if (container) {
    container.insertAdjacentHTML('beforeend', messageBubble('user', text));
    const typing = document.createElement('div');
    typing.className = 'message message--assistant';
    typing.id = 'typing-msg';
    typing.innerHTML = `
      <div class="message-sender">${esc(agent.display_name)}</div>
      <div class="typing-indicator">
        <div class="typing-dot"></div><div class="typing-dot"></div><div class="typing-dot"></div>
      </div>`;
    container.appendChild(typing);
    container.scrollTop = container.scrollHeight;
  }

  let accumulated = '';

  await streamChat({
    url: `/api/brands/${brand.id}/agents/${agent.id}/chat`,
    body: { message: text },
    onToken(t) {
      accumulated += t;
      const typingEl = document.getElementById('typing-msg');
      if (typingEl) {
        typingEl.innerHTML = `
          <div class="message-sender">${esc(agent.display_name)}</div>
          <div class="message-bubble">${renderMarkdown(accumulated)}</div>`;
      }
      if (container) container.scrollTop = container.scrollHeight;
    },
    onDone() {
      const typingEl = document.getElementById('typing-msg');
      if (typingEl) {
        typingEl.id = '';
        typingEl.innerHTML = `
          <div class="message-sender">${esc(agent.display_name)}</div>
          <div class="message-bubble">${renderMarkdown(accumulated)}</div>`;
      }
      input.disabled = false; sendBtn.disabled = false; input.focus();
      if (container) container.scrollTop = container.scrollHeight;
    },
    onError(err) {
      document.getElementById('typing-msg')?.remove();
      if (container) {
        container.insertAdjacentHTML('beforeend',
          `<div style="color:var(--red);font-size:12px;padding:8px 4px">Error: ${esc(err)}</div>`);
      }
      input.disabled = false; sendBtn.disabled = false;
    },
  });
}

// ── Shared helpers ────────────────────────────────────────────────────────────
function messageBubble(role, content) {
  const isUser    = role === 'user';
  const senderLabel = isUser ? 'You' : 'Assistant';
  const bubbleHTML  = isUser
    ? `<div class="message-bubble">${esc(content).replace(/\n/g, '<br>')}</div>`
    : `<div class="message-bubble">${renderMarkdown(content)}</div>`;
  return `
<div class="message message--${isUser ? 'user' : 'assistant'}">
  <div class="message-sender">${senderLabel}</div>
  ${bubbleHTML}
</div>`;
}

function queueCard(r) {
  return `
<div class="queue-card">
  <div class="qc-meta">
    <span class="qc-agent">${esc(r.agent_display_name)}</span>
    <span class="qc-date">${fmtDate(r.created_at)}</span>
  </div>
  <div class="qc-body">${esc(trunc(r.content, 300))}</div>
  <div class="qc-actions">
    <button class="btn btn--success" data-approve="${r.id}">✓ Approve</button>
    <button class="btn btn--danger"  data-reject="${r.id}">✗ Reject</button>
  </div>
</div>`;
}

function autoResize(el) {
  el.style.height = 'auto';
  el.style.height = Math.min(el.scrollHeight, 160) + 'px';
}

// ── View: Knowledge Base ──────────────────────────────────────────────────────
function ytBadge(status) {
  const m = { pending: 'Pending', processing: 'Processing…', done: 'Done', error: 'Error', 'no-output': 'No Output' };
  return `<span class="badge badge--yt-${status}">${m[status] ?? status}</span>`;
}

let _kbLogSource = null;

async function mountKnowledge(app) {
  const [queue, status] = await Promise.all([
    API.get('/api/knowledge/queue'),
    API.get('/api/knowledge/status'),
  ]);
  S.kbPendingCount = status.counts.pending || 0;

  const pendingCount = status.counts.pending || 0;
  const hasProcessing = status.running || (status.counts.processing || 0) > 0;

  app.innerHTML = `
<div class="page-body">
  <div class="page-header">
    <div>
      <h1 class="page-title">Knowledge Base</h1>
      <p class="page-sub">YouTube → agent knowledge files · /root/knowledge/</p>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2 class="panel-title">Add Video</h2>
    </div>
    <div class="kb-form">
      <div class="kb-form-group">
        <label class="kb-form-label">YouTube URL</label>
        <input class="kb-input" id="kb-url" type="url" placeholder="https://youtu.be/…">
      </div>
      <div class="kb-form-group">
        <label class="kb-form-label">Speaker Name</label>
        <input class="kb-input" id="kb-speaker" type="text" placeholder="e.g. Emil Olesen">
      </div>
      <button class="btn btn--primary" id="kb-add-btn">Add to Queue</button>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <h2 class="panel-title">
        Queue
        <span class="count">${queue.length}</span>
      </h2>
      <button class="btn btn--primary btn--sm" id="kb-process-btn"
        ${hasProcessing ? 'disabled' : ''}>
        ${hasProcessing ? '⏳ Processing…' : `▶ Process Pending (${pendingCount})`}
      </button>
    </div>
    ${queue.length === 0
      ? `<div class="empty">No videos in queue yet</div>`
      : `<table class="kb-table">
          <thead>
            <tr>
              <th>Speaker</th>
              <th>URL</th>
              <th>Status</th>
              <th>Added</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            ${queue.map(r => `
              <tr>
                <td><strong>${esc(r.speaker)}</strong></td>
                <td>
                  <div class="kb-url"><a href="${esc(r.url)}" target="_blank" style="color:var(--accent)">${esc(r.url)}</a></div>
                  ${r.output_files ? `<div class="kb-files">📁 ${esc(r.output_files).split('; ').length} files</div>` : ''}
                  ${r.error_msg    ? `<div class="kb-error">⚠ ${esc(trunc(r.error_msg, 120))}</div>` : ''}
                </td>
                <td>${ytBadge(r.status)}</td>
                <td style="white-space:nowrap;color:var(--text2);font-size:12px">${fmtDate(r.added_at)}</td>
                <td>
                  <div class="kb-actions">
                    ${r.status === 'error' || r.status === 'no-output'
                      ? `<button class="btn btn--sm" data-retry="${r.id}">↺ Retry</button>`
                      : ''}
                    <button class="btn btn--sm btn--ghost" data-del="${r.id}">✕</button>
                  </div>
                </td>
              </tr>
            `).join('')}
          </tbody>
        </table>`
    }
  </div>

  <div class="panel" id="kb-log-panel">
    <div class="panel-header">
      <h2 class="panel-title">Processing Log</h2>
      ${hasProcessing ? `<span class="badge badge--yt-processing">Live</span>` : ''}
    </div>
    <div class="log-box" id="kb-log">
      ${hasProcessing ? '<span class="log-dim">Connecting to log stream…</span>' : '<span class="log-dim">Press ▶ Process Pending to start.</span>'}
    </div>
  </div>
</div>`;

  document.getElementById('kb-add-btn').onclick = async () => {
    const url     = document.getElementById('kb-url').value.trim();
    const speaker = document.getElementById('kb-speaker').value.trim();
    if (!url || !speaker) { alert('Both URL and speaker name are required.'); return; }
    const btn = document.getElementById('kb-add-btn');
    btn.disabled = true;
    try {
      await API.post('/api/knowledge/queue', { url, speaker });
      document.getElementById('kb-url').value = '';
      document.getElementById('kb-speaker').value = '';
      mountKnowledge(app);
    } finally { btn.disabled = false; }
  };

  ['kb-url', 'kb-speaker'].forEach(id => {
    document.getElementById(id)?.addEventListener('keydown', e => {
      if (e.key === 'Enter') document.getElementById('kb-add-btn')?.click();
    });
  });

  document.getElementById('kb-process-btn').onclick = async () => {
    const btn = document.getElementById('kb-process-btn');
    btn.disabled = true;
    const res = await API.post('/api/knowledge/process');
    if (res.ok) {
      startLogStream(app);
    } else {
      btn.disabled = false;
      alert(res.message || 'Could not start processing');
    }
  };

  app.querySelectorAll('[data-del]').forEach(btn => {
    btn.onclick = async () => {
      if (!confirm('Remove this item from the queue?')) return;
      await API.delete(`/api/knowledge/queue/${btn.dataset.del}`);
      mountKnowledge(app);
    };
  });

  app.querySelectorAll('[data-retry]').forEach(btn => {
    btn.onclick = async () => {
      await API.post(`/api/knowledge/queue/${btn.dataset.retry}/retry`);
      mountKnowledge(app);
    };
  });

  if (hasProcessing) startLogStream(app);
}

function startLogStream(app) {
  if (_kbLogSource) { _kbLogSource.close(); _kbLogSource = null; }

  const logBox = document.getElementById('kb-log');
  if (logBox) logBox.innerHTML = '';

  const es = new EventSource('/api/knowledge/log');
  _kbLogSource = es;

  es.onmessage = (e) => {
    const data = JSON.parse(e.data);
    if (data.done) {
      es.close(); _kbLogSource = null;
      setTimeout(() => { if (S.view === 'knowledge') mountKnowledge(app); }, 600);
      return;
    }
    if (data.line) {
      const box = document.getElementById('kb-log');
      if (!box) return;
      const line = data.line;
      const span = document.createElement('span');
      if (line.startsWith('  ✓')) span.className = 'log-ok';
      else if (line.includes('✗') || line.includes('FEJL') || line.includes('error')) span.className = 'log-err';
      else if (line.startsWith('===')) span.className = 'log-head';
      span.textContent = line;
      box.appendChild(span);
      box.appendChild(document.createTextNode('\n'));
      box.scrollTop = box.scrollHeight;
    }
  };

  es.onerror = () => { es.close(); _kbLogSource = null; };
}

// ── Poll sidebar ──────────────────────────────────────────────────────────────
setInterval(async () => {
  try {
    for (const b of S.brands) {
      const agents = await API.get(`/api/brands/${b.id}/agents`);
      S.brandAgents[b.slug] = agents;
    }
    const st = await API.get('/api/knowledge/status');
    S.kbPendingCount = st.counts.pending || 0;
    renderSidebar();
  } catch (_) {}
}, 30_000);

// ── Boot ──────────────────────────────────────────────────────────────────────
(async () => {
  await loadSidebar();
  route();
})();
