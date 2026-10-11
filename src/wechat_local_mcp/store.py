"""Durable received messages and an idempotent outgoing request ledger."""

from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import time


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def unix_seconds(value, fallback: float) -> float:
    """Normalize modern OneBot seconds or wechat_chatter milliseconds to seconds.

    The upstream wechat_chatter callback uses UnixMilli; standard OneBot events
    may use Unix seconds. Contemporary millisecond epochs exceed 1e11, whereas
    contemporary second epochs do not. Preserve the original value in event_json.
    """
    if value is None or value == "":
        return fallback
    timestamp = float(value)
    if not math.isfinite(timestamp):
        raise ValueError("Message time must be a finite Unix timestamp")
    return timestamp / 1000 if abs(timestamp) >= 100_000_000_000 else timestamp


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE,
                    chat_id TEXT NOT NULL, chat_type TEXT NOT NULL,
                    message_id TEXT, sender_id TEXT, text TEXT NOT NULL,
                    timestamp REAL NOT NULL, received_at REAL NOT NULL,
                    source TEXT NOT NULL, event_json TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id, id);
                CREATE TABLE IF NOT EXISTS outgoing (
                    request_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL,
                    created_at REAL NOT NULL, updated_at REAL NOT NULL,
                    result_json TEXT NOT NULL
                );
            """)
            # Repair caches written before timestamp normalization. Applying the
            # same magnitude boundary makes this migration safe to run again.
            db.execute("UPDATE messages SET timestamp = timestamp / 1000.0 WHERE ABS(timestamp) >= 100000000000")
            # Phone -> File Transfer Assistant is emitted by wechat_chatter
            # with receiver=filehelper in self_id and the account in user_id.
            db.execute("UPDATE messages SET chat_id = 'filehelper' WHERE chat_type = 'private' AND json_extract(event_json, '$.self_id') = 'filehelper'")
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def ingest(self, event: dict) -> dict:
        if event.get("post_type") not in {"message", "message_sent"}:
            return {"accepted": False, "reason": "not_a_message"}
        chat_type = "group" if event.get("group_id") else "private"
        chat_id = str(event.get("group_id") or event.get("user_id") or "")
        if not chat_id:
            raise ValueError("Message event is missing group_id/user_id")
        raw_chat_id = chat_id
        if chat_type == "private" and event.get("self_id") == "filehelper":
            chat_id = "filehelper"
        segments = event.get("message", [])
        if isinstance(segments, str):
            text = segments
        elif isinstance(segments, list):
            text = "".join(
                str(segment.get("data", {}).get("text", ""))
                if segment.get("type") == "text" else f"[{segment.get('type', 'unknown')}]"
                for segment in segments if isinstance(segment, dict)
            )
        else:
            text = str(event.get("raw_message", ""))
        raw = encode(event)
        message_id = str(event.get("message_id") or "")
        identity = [str(event.get("self_id", "")), raw_chat_id, message_id]
        event_key = hashlib.sha256((encode(identity) if message_id else raw).encode()).hexdigest()
        now = time.time()
        with self.connect() as db:
            cursor = db.execute(
                "INSERT OR IGNORE INTO messages(event_key,chat_id,chat_type,message_id,sender_id,text,timestamp,received_at,source,event_json) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (event_key, chat_id, chat_type, message_id, str(event.get("user_id", "")), text,
                 unix_seconds(event.get("time"), now), now, "onebot_webhook", raw),
            )
            inserted = cursor.rowcount > 0
            row = db.execute("SELECT id FROM messages WHERE event_key=?", (event_key,)).fetchone()
        return {"accepted": True, "duplicate": not inserted, "id": row["id"]}

    def messages(self, chat_id: str = "", limit: int = 50, after_id: int = 0) -> list[dict]:
        if not 1 <= limit <= 200 or after_id < 0:
            raise ValueError("limit must be 1..200 and after_id must be nonnegative")
        where, args = ["id > ?"], [after_id]
        if chat_id:
            where.append("chat_id = ?")
            args.append(chat_id)
        order = "ASC" if after_id else "DESC"
        with self.connect() as db:
            rows = db.execute(
                f"SELECT id,chat_id,chat_type,message_id,sender_id,text,timestamp,received_at,source FROM messages WHERE {' AND '.join(where)} ORDER BY id {order} LIMIT ?",
                (*args, limit),
            ).fetchall()
        values = [dict(row) for row in rows]
        return values if after_id else list(reversed(values))

    def chats(self, limit: int = 50) -> list[dict]:
        if not 1 <= limit <= 200:
            raise ValueError("limit must be 1..200")
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT chat_id,chat_type,COUNT(*) AS cached_messages,MAX(received_at) AS last_received_at FROM messages GROUP BY chat_id,chat_type ORDER BY last_received_at DESC LIMIT ?", (limit,)
            ).fetchall()]

    def stats(self) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT COUNT(*) AS cached_messages, MAX(received_at) AS last_received_at FROM messages").fetchone()
            return dict(row)

    def begin_send(self, request_id: str, payload: dict) -> tuple[bool, dict]:
        fingerprint = hashlib.sha256(encode(payload).encode()).hexdigest()
        now = time.time()
        result = {"request_id": request_id, "delivery_status": "unverified", "transmission": "in_progress", "automatic_retry": False, "check_wechat_ui": True, "message": "Request in progress or process stopped before recording its outcome; do not automatically resend."}
        with self.connect() as db:
            inserted = db.execute("INSERT OR IGNORE INTO outgoing VALUES (?,?,?,?,?)", (request_id, fingerprint, now, now, encode(result))).rowcount > 0
            row = db.execute("SELECT fingerprint,result_json FROM outgoing WHERE request_id=?", (request_id,)).fetchone()
            if row["fingerprint"] != fingerprint:
                raise ValueError("request_id was already used with a different message or recipient")
            return inserted, json.loads(row["result_json"])

    def finish_send(self, request_id: str, result: dict) -> dict:
        result = {**result, "request_id": request_id}
        with self.connect() as db:
            db.execute("UPDATE outgoing SET updated_at=?,result_json=? WHERE request_id=?", (time.time(), encode(result), request_id))
        return result

    def send_status(self, request_id: str) -> dict:
        with self.connect() as db:
            row = db.execute("SELECT result_json FROM outgoing WHERE request_id=?", (request_id,)).fetchone()
        return json.loads(row["result_json"]) if row else {"request_id": request_id, "delivery_status": "not_found"}
