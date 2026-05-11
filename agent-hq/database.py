import os
import sqlite3
from datetime import datetime, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "agent_hq.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    if os.path.exists(DB_PATH):
        try:
            conn = sqlite3.connect(DB_PATH)
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            conn.close()
            if "brands" not in tables:
                os.remove(DB_PATH)
        except Exception:
            os.remove(DB_PATH)

    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS brands (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            slug       TEXT NOT NULL UNIQUE,
            context    TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS agents (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            brand_id     INTEGER NOT NULL,
            name         TEXT NOT NULL,
            display_name TEXT NOT NULL,
            role         TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'idle'
                CHECK(status IN ('idle','working','waiting_approval')),
            FOREIGN KEY (brand_id) REFERENCES brands(id),
            UNIQUE(brand_id, name)
        );

        CREATE TABLE IF NOT EXISTS reports (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id   INTEGER NOT NULL,
            brand_id   INTEGER NOT NULL,
            content    TEXT NOT NULL,
            created_at TEXT NOT NULL,
            status     TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','approved','rejected')),
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        );

        CREATE TABLE IF NOT EXISTS tasks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id    INTEGER NOT NULL,
            brand_id    INTEGER NOT NULL,
            description TEXT NOT NULL,
            created_at  TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending'
                CHECK(status IN ('pending','in_progress','completed','failed')),
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        );

        CREATE TABLE IF NOT EXISTS conversations (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id   INTEGER NOT NULL UNIQUE,
            brand_id   INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (agent_id) REFERENCES agents(id),
            FOREIGN KEY (brand_id) REFERENCES brands(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            conversation_id INTEGER NOT NULL,
            role            TEXT NOT NULL CHECK(role IN ('user','assistant')),
            content         TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS youtube_queue (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            url          TEXT NOT NULL,
            speaker      TEXT NOT NULL,
            status       TEXT NOT NULL DEFAULT 'pending',
            added_at     TEXT NOT NULL,
            processed_at TEXT,
            output_files TEXT,
            error_msg    TEXT
        );
    """)
    conn.commit()

    # Migration: add context column to existing databases
    try:
        conn.execute("ALTER TABLE brands ADD COLUMN context TEXT NOT NULL DEFAULT ''")
        conn.commit()
    except Exception:
        pass

    conn.close()


def seed_data():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM brands")
    if c.fetchone()[0] > 0:
        conn.close()
        return

    now = datetime.utcnow()

    def ts(delta_h=0):
        return (now - timedelta(hours=delta_h)).isoformat()

    jch_context = """Produkt: Health tracker wristband — dansk premium produkt
Pris: DKK 2.499 vejledende
Målgruppe: Ambitiøse professionelle, 28-45 år, Skandinavien
Salgskanaler: Meta, TikTok, YouTube, nordiske influencers
Platform: DTC via Shopify + Amazon Nordic"""

    c.execute("INSERT INTO brands (name, slug, context, created_at) VALUES (?,?,?,?)",
              ("Jens Christian Health", "jens-christian-health", jch_context, ts()))
    brand_id = c.lastrowid

    agents = [
        (brand_id, "creative-strategist", "Creative Strategist", "creative-strategist", "working"),
        (brand_id, "copy-agent",           "Copy Agent",           "copy-agent",           "waiting_approval"),
        (brand_id, "performance-analyst",  "Performance Analyst",  "performance-analyst",  "working"),
        (brand_id, "lifecycle-crm",        "Lifecycle CRM",        "lifecycle-crm",        "idle"),
    ]
    c.executemany(
        "INSERT INTO agents (brand_id, name, display_name, role, status) VALUES (?,?,?,?,?)",
        agents,
    )
    conn.commit()

    c.execute("SELECT id, name FROM agents WHERE brand_id=?", (brand_id,))
    am = {row["name"]: row["id"] for row in c.fetchall()}

    reports = [
        (am["creative-strategist"], brand_id,
         "Q2 Brand Strategy Analysis\n\nKey findings:\n"
         "- Brand sentiment up 12% vs Q1\n"
         "- Top performing creative: video testimonials (CTR +34%)\n"
         "- Audience segment 28-38F outperforming all others\n\n"
         "Recommended focus: UGC campaign for summer launch.\n"
         "Three concepts ready for director review.",
         "pending", ts(1)),
        (am["copy-agent"], brand_id,
         "Email Campaign Copy — Newsletter #47\n\n"
         "Subject line A/B variants (5 tested):\n"
         "  1. 'Your May report is ready'       → 24% open rate\n"
         "  2. 'Here's what worked this month'  → 31% open rate ✓ WINNER\n\n"
         "Body copy finalised. CTA revised to reduce friction.",
         "pending", ts(3)),
        (am["performance-analyst"], brand_id,
         "Weekly Performance Report — W18\n\n"
         "CPA:  €12.40  ↓8% WoW  ✓\n"
         "ROAS: 3.2x    ↑0.4 WoW ✓\n"
         "CTR:  2.1%    flat\n\n"
         "⚠ Anomaly: Campaign #44 showing 40% CTR drop on mobile.\n"
         "Root cause: iOS 18 rendering bug. Recommend pause + creative swap.",
         "approved", ts(12)),
    ]
    c.executemany(
        "INSERT INTO reports (agent_id, brand_id, content, status, created_at) VALUES (?,?,?,?,?)",
        reports,
    )

    tasks = [
        (am["creative-strategist"], brand_id, "Develop Q3 creative brief for paid social", "in_progress", ts(5)),
        (am["creative-strategist"], brand_id, "Review competitor ad library — Meta + TikTok", "completed", ts(48)),
        (am["copy-agent"],          brand_id, "Write 10 ad variants for summer campaign", "pending", ts(2)),
        (am["copy-agent"],          brand_id, "Revise landing page headline — 3 variants", "in_progress", ts(8)),
        (am["performance-analyst"], brand_id, "Investigate mobile CTR drop on Campaign #44", "in_progress", ts(4)),
        (am["lifecycle-crm"],       brand_id, "Segment re-engagement list by last purchase", "completed", ts(30)),
        (am["lifecycle-crm"],       brand_id, "QA win-back flow in staging", "in_progress", ts(6)),
    ]
    c.executemany(
        "INSERT INTO tasks (agent_id, brand_id, description, status, created_at) VALUES (?,?,?,?,?)",
        tasks,
    )

    conn.commit()
    conn.close()
