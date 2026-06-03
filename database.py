import sqlite3
import uuid
from config import DB_PATH


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            full_name   TEXT,
            link_token  TEXT UNIQUE,
            joined_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS questions (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id        INTEGER NOT NULL,
            asker_id        INTEGER,
            question_text   TEXT NOT NULL,
            answer_text     TEXT,
            asked_at        TEXT DEFAULT (datetime('now')),
            answered_at     TEXT,
            identity_revealed INTEGER DEFAULT 0,
            FOREIGN KEY (owner_id) REFERENCES users(user_id)
        );

        CREATE TABLE IF NOT EXISTS sponsor_channels (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            channel_id  TEXT UNIQUE NOT NULL,
            title       TEXT NOT NULL,
            invite_link TEXT,
            added_at    TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS channel_subs (
            user_id     INTEGER NOT NULL,
            channel_id  TEXT NOT NULL,
            checked_at  TEXT DEFAULT (datetime('now')),
            PRIMARY KEY (user_id, channel_id)
        );
    """)

    conn.commit()
    conn.close()


# ─── USERS ────────────────────────────────────────────────────────────────────

def get_or_create_user(user_id: int, username: str, full_name: str) -> dict:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    if row is None:
        token = uuid.uuid4().hex[:12]
        cur.execute(
            "INSERT INTO users (user_id, username, full_name, link_token) VALUES (?, ?, ?, ?)",
            (user_id, username, full_name, token)
        )
        conn.commit()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        row = cur.fetchone()
    conn.close()
    return dict(row)


def get_user_by_id(user_id: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_by_token(token: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE link_token = ?", (token,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_all_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def count_users():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = cur.fetchone()[0]
    conn.close()
    return count


# ─── QUESTIONS ────────────────────────────────────────────────────────────────

def save_question(owner_id: int, asker_id: int, text: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO questions (owner_id, asker_id, question_text) VALUES (?, ?, ?)",
        (owner_id, asker_id, text)
    )
    qid = cur.lastrowid
    conn.commit()
    conn.close()
    return qid


def get_question(qid: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM questions WHERE id = ?", (qid,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def save_answer(qid: int, answer_text: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "UPDATE questions SET answer_text = ?, answered_at = datetime('now') WHERE id = ?",
        (answer_text, qid)
    )
    conn.commit()
    conn.close()


def mark_identity_revealed(qid: int):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE questions SET identity_revealed = 1 WHERE id = ?", (qid,))
    conn.commit()
    conn.close()


def count_questions():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM questions")
    c = cur.fetchone()[0]
    conn.close()
    return c


def count_answers():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM questions WHERE answer_text IS NOT NULL")
    c = cur.fetchone()[0]
    conn.close()
    return c


def get_questions_for_owner(owner_id: int, limit: int = 20) -> list[dict]:
    """Get questions received by the owner, newest first."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM questions WHERE owner_id = ? ORDER BY asked_at DESC LIMIT ?",
        (owner_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_recent_questions_admin(limit: int = 20) -> list[dict]:
    """Admin: get recent questions with asker and owner info joined."""
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            q.id, q.question_text, q.answer_text, q.asked_at, q.answered_at,
            q.identity_revealed,
            owner.full_name  AS owner_name,  owner.username  AS owner_username,
            asker.full_name  AS asker_name,  asker.username  AS asker_username
        FROM questions q
        LEFT JOIN users owner ON q.owner_id = owner.user_id
        LEFT JOIN users asker ON q.asker_id = asker.user_id
        ORDER BY q.asked_at DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ─── SPONSOR CHANNELS ─────────────────────────────────────────────────────────

def add_channel(channel_id: str, title: str, invite_link: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO sponsor_channels (channel_id, title, invite_link) VALUES (?, ?, ?)",
        (channel_id, title, invite_link)
    )
    conn.commit()
    conn.close()


def remove_channel(channel_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM sponsor_channels WHERE channel_id = ?", (channel_id,))
    conn.commit()
    conn.close()


def get_all_channels():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sponsor_channels")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def record_sub(user_id: int, channel_id: str):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT OR REPLACE INTO channel_subs (user_id, channel_id) VALUES (?, ?)",
        (user_id, channel_id)
    )
    conn.commit()
    conn.close()


def count_subs(channel_id: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM channel_subs WHERE channel_id = ?", (channel_id,))
    c = cur.fetchone()[0]
    conn.close()
    return c
