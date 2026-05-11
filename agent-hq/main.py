import os
import json
import asyncio
from pathlib import Path
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import anthropic

from database import get_conn, init_db, seed_data

init_db()
seed_data()

app = FastAPI()

KNOWLEDGE_DIR = Path("/root/knowledge")
API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=API_KEY) if API_KEY else None

AGENT_ROLES = {
    "creative-strategist": "kreative strategier, kampagnekoncepeter, brand positioning, UGC-koncepter og creative briefs",
    "copy-agent": "konverterende copy — Meta-annoncer, email, landing pages, TikTok-scripts og produkttekster",
    "performance-analyst": "marketing performance analyse, ROAS/CPA/CTR/LTV, kanalanalyse, anomaly detection og budget-anbefalinger",
    "lifecycle-crm": "Klaviyo email-flows, segmentering, retention-strategier, Shopify + Segment integration og win-back kampagner",
}

BRAND_CONTEXT = """Brand: Jens Christian Health
- Dansk premium health tracker wristband, DKK 2.499 vejl.
- Målgruppe: Ambitiøse professionelle 28-45 år, Skandinavien
- Kanaler: Meta, TikTok, YouTube, nordiske influencers
- Salg: DTC via Shopify + Amazon Nordic"""


def get_knowledge() -> str:
    parts = []
    if not KNOWLEDGE_DIR.exists():
        return ""
    for agent_dir in sorted(KNOWLEDGE_DIR.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("_"):
            continue
        for sub_dir in sorted(agent_dir.iterdir()):
            if not sub_dir.is_dir():
                continue
            kdir = sub_dir / "_knowledge"
            if not kdir.exists():
                continue
            for f in sorted(kdir.glob("*.md"), reverse=True)[:3]:
                try:
                    text = f.read_text(encoding="utf-8")
                    parts.append(f"=== {agent_dir.name}/{sub_dir.name}/{f.name} ===\n{text[:4000]}")
                except Exception:
                    pass
    return "\n\n".join(parts)


def build_system_prompt(agent_name: str) -> str:
    role = AGENT_ROLES.get(agent_name, agent_name)
    knowledge = get_knowledge()

    if not knowledge:
        return f"""Du er {agent_name} for Jens Christian Health.
{BRAND_CONTEXT}

Din rolle: {role}.

VIGTIGT: Du har endnu ikke adgang til nogen vidensbase. Sig det eksplicit til brugeren og bed dem uploade YouTube-transkripter via Knowledge Base sektionen. Svar ikke med generel viden — kun med hvad der er i din vidensbase.

Svar altid på dansk."""

    return f"""Du er {agent_name} for Jens Christian Health.
{BRAND_CONTEXT}

Din rolle: {role}.

Du må KUN basere dine svar på den vidensbase der er givet nedenfor. Brug ikke din generelle træningsviden til at lave anbefalinger — hvis svaret ikke findes i vidensbasen, sig det eksplicit og referér til hvilke emner der er dækket.

Svar altid på dansk.

Vidensbase (fra YouTube-transkripter processeret af dine specialistagenter):
{knowledge}"""


async def sse_stream(gen: AsyncGenerator) -> StreamingResponse:
    return StreamingResponse(gen, media_type="text/event-stream; charset=utf-8",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


async def stream_claude(messages: list, system: str = "") -> AsyncGenerator[str, None]:
    if not client:
        yield f"data: {json.dumps({'error': 'API key not set'})}\n\n"
        return
    try:
        kwargs = dict(model="claude-sonnet-4-6", max_tokens=2048, messages=messages)
        if system:
            kwargs["system"] = system
        with client.messages.stream(**kwargs) as stream:
            for chunk in stream.text_stream:
                yield f"data: {json.dumps({'text': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


@app.get("/api/config")
def get_config():
    knowledge = get_knowledge()
    return {"api_key_set": bool(API_KEY), "knowledge_loaded": bool(knowledge)}


@app.get("/api/brands")
def list_brands():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM brands ORDER BY id").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/brands/{brand_id}/agents")
def list_agents(brand_id: int):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM agents WHERE brand_id=? ORDER BY id", (brand_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.get("/api/brands/{brand_id}/stats")
def brand_stats(brand_id: int):
    conn = get_conn()
    active_agents   = conn.execute("SELECT COUNT(*) FROM agents WHERE brand_id=? AND status!='idle'", (brand_id,)).fetchone()[0]
    pending         = conn.execute("SELECT COUNT(*) FROM reports WHERE brand_id=? AND status='pending'", (brand_id,)).fetchone()[0]
    active_tasks    = conn.execute("SELECT COUNT(*) FROM tasks WHERE brand_id=? AND status IN ('pending','in_progress')", (brand_id,)).fetchone()[0]
    completed_tasks = conn.execute("SELECT COUNT(*) FROM tasks WHERE brand_id=? AND status='completed'", (brand_id,)).fetchone()[0]
    conn.close()
    return {"active_agents": active_agents, "pending_approvals": pending,
            "active_tasks": active_tasks, "completed_tasks": completed_tasks}


@app.get("/api/brands/{brand_id}/queue")
def approval_queue(brand_id: int):
    conn = get_conn()
    rows = conn.execute("""
        SELECT r.*, a.display_name as agent_display_name
        FROM reports r JOIN agents a ON r.agent_id=a.id
        WHERE r.brand_id=? AND r.status='pending'
        ORDER BY r.created_at DESC
    """, (brand_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


class StatusUpdate(BaseModel):
    status: str


@app.patch("/api/agents/{agent_id}")
def update_agent_status(agent_id: int, body: StatusUpdate):
    conn = get_conn()
    conn.execute("UPDATE agents SET status=? WHERE id=?", (body.status, agent_id))
    conn.commit()
    conn.close()
    return {"ok": True}


class ReportUpdate(BaseModel):
    status: str


@app.patch("/api/reports/{report_id}")
def update_report(report_id: int, body: ReportUpdate):
    conn = get_conn()
    conn.execute("UPDATE reports SET status=? WHERE id=?", (body.status, report_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/brands/{brand_id}/agents/{agent_id}/messages")
def get_messages(brand_id: int, agent_id: int):
    conn = get_conn()
    conv = conn.execute("SELECT id FROM conversations WHERE agent_id=?", (agent_id,)).fetchone()
    if not conv:
        conn.close()
        return []
    rows = conn.execute(
        "SELECT role, content, created_at FROM messages WHERE conversation_id=? ORDER BY id",
        (conv["id"],)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.delete("/api/brands/{brand_id}/agents/{agent_id}/messages")
def clear_messages(brand_id: int, agent_id: int):
    conn = get_conn()
    conv = conn.execute("SELECT id FROM conversations WHERE agent_id=?", (agent_id,)).fetchone()
    if conv:
        conn.execute("DELETE FROM messages WHERE conversation_id=?", (conv["id"],))
        conn.execute("DELETE FROM conversations WHERE id=?", (conv["id"],))
        conn.commit()
    conn.close()
    return {"ok": True}


class AgentChatRequest(BaseModel):
    message: str


class TestChatRequest(BaseModel):
    messages: list


@app.post("/api/brands/{brand_id}/agents/{agent_id}/chat")
async def agent_chat(brand_id: int, agent_id: int, body: AgentChatRequest):
    conn = get_conn()
    agent = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    if not agent:
        conn.close()
        raise HTTPException(404, "Agent not found")

    from datetime import datetime
    now = datetime.utcnow().isoformat()

    conv = conn.execute("SELECT id FROM conversations WHERE agent_id=?", (agent_id,)).fetchone()
    if not conv:
        conn.execute("INSERT INTO conversations (agent_id, brand_id, created_at) VALUES (?,?,?)",
                     (agent_id, brand_id, now))
        conn.commit()
        conv = conn.execute("SELECT id FROM conversations WHERE agent_id=?", (agent_id,)).fetchone()

    conv_id = conv["id"]
    history = conn.execute(
        "SELECT role, content FROM messages WHERE conversation_id=? ORDER BY id",
        (conv_id,)
    ).fetchall()

    messages = [dict(r) for r in history]
    messages.append({"role": "user", "content": body.message})

    conn.execute("INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                 (conv_id, "user", body.message, now))
    conn.commit()
    conn.close()

    system = build_system_prompt(agent["name"])
    accumulated = []

    async def gen():
        async for chunk in stream_claude(messages, system):
            if chunk.startswith("data: ") and chunk.strip() != "data: [DONE]":
                try:
                    obj = json.loads(chunk[6:])
                    if obj.get("text"):
                        accumulated.append(obj["text"])
                except Exception:
                    pass
            yield chunk
        if accumulated:
            full = "".join(accumulated)
            c = get_conn()
            c.execute("INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?,?,?,?)",
                      (conv_id, "assistant", full, now))
            c.commit()
            c.close()

    return await sse_stream(gen())


@app.post("/api/chat/test")
async def test_chat(body: TestChatRequest):
    return await sse_stream(stream_claude(body.messages))


class QueueItem(BaseModel):
    url: str
    speaker: str


@app.get("/api/knowledge/queue")
def get_queue():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM youtube_queue ORDER BY added_at DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


@app.post("/api/knowledge/queue")
def add_to_queue(item: QueueItem):
    from datetime import datetime
    conn = get_conn()
    conn.execute(
        "INSERT INTO youtube_queue (url, speaker, status, added_at) VALUES (?,?,?,?)",
        (item.url, item.speaker, "pending", datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/knowledge/queue/{item_id}")
def delete_queue_item(item_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM youtube_queue WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/knowledge/queue/{item_id}/retry")
def retry_queue_item(item_id: int):
    conn = get_conn()
    conn.execute("UPDATE youtube_queue SET status='pending', error_msg=NULL WHERE id=?", (item_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/knowledge/status")
def knowledge_status():
    conn = get_conn()
    rows = conn.execute("SELECT status, COUNT(*) as n FROM youtube_queue GROUP BY status").fetchall()
    conn.close()
    counts = {r["status"]: r["n"] for r in rows}
    return {"counts": counts, "running": _processing}


_log_queue: asyncio.Queue = asyncio.Queue()
_processing = False


@app.post("/api/knowledge/process")
async def start_processing():
    global _processing
    if _processing:
        return {"ok": False, "message": "Already running"}
    _processing = True
    asyncio.create_task(run_processor())
    return {"ok": True}


async def run_processor():
    global _processing
    conn = get_conn()
    pending = conn.execute("SELECT * FROM youtube_queue WHERE status='pending'").fetchall()
    conn.close()

    for row in pending:
        await _log_queue.put({"line": f"=== [{row['speaker']}] {row['url']} ==="})
        conn = get_conn()
        conn.execute("UPDATE youtube_queue SET status='processing' WHERE id=?", (row["id"],))
        conn.commit()
        conn.close()
        try:
            proc = await asyncio.create_subprocess_exec(
                "python3", "/root/processor/process.py", row["speaker"], row["url"],
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
            )
            lines = []
            async for line in proc.stdout:
                text = line.decode("utf-8", errors="replace").rstrip()
                lines.append(text)
                await _log_queue.put({"line": text})
            await proc.wait()
            from datetime import datetime
            conn = get_conn()
            if proc.returncode == 0:
                conn.execute("UPDATE youtube_queue SET status='done', processed_at=? WHERE id=?",
                             (datetime.utcnow().isoformat(), row["id"]))
                await _log_queue.put({"line": f"  ✓ Done"})
            else:
                err = "\n".join(lines[-3:])
                conn.execute("UPDATE youtube_queue SET status='error', error_msg=? WHERE id=?",
                             (err[:500], row["id"]))
                await _log_queue.put({"line": f"  ✗ Error"})
            conn.commit()
            conn.close()
        except Exception as e:
            conn = get_conn()
            conn.execute("UPDATE youtube_queue SET status='error', error_msg=? WHERE id=?",
                         (str(e)[:500], row["id"]))
            conn.commit()
            conn.close()
            await _log_queue.put({"line": f"  ✗ {e}"})

    await _log_queue.put({"done": True})
    _processing = False


@app.get("/api/knowledge/log")
async def knowledge_log():
    async def gen():
        while True:
            try:
                item = await asyncio.wait_for(_log_queue.get(), timeout=30)
                yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
                if item.get("done"):
                    break
            except asyncio.TimeoutError:
                yield "data: {\"ping\": true}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream; charset=utf-8",
                             headers={"Cache-Control": "no-cache"})


app.mount("/static", StaticFiles(directory="/root/agent-hq/static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return Path("/root/agent-hq/static/index.html").read_text(encoding="utf-8")
