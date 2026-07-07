"""Dual-layer memory system.

Layer 1 — Episodic (what happened): SQLite table of timestamped events.
Layer 2 — Semantic (who the user is): JSON profile that grows over time.
Optional:  ChromaDB vector store for fuzzy recall of past events.
"""

import json
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Any, Optional

from config.settings import settings
from core.logger import get_logger

log = get_logger("memory")

try:
    import chromadb

    _HAS_CHROMA = True
except Exception:  # chromadb is optional — memory works without vector recall
    _HAS_CHROMA = False


DEFAULT_PROFILE: dict = {
    "name": "",
    "occupation": "",
    "skills": [],
    "writing_style": "",
    "job_preferences": {"roles": [], "locations": [], "salary_min": 0, "avoid": []},
    "posting_style": {"linkedin_tone": "", "post_frequency": "", "topics": []},
    "schedule": {"morning_routine_time": "08:00", "work_hours": "09:00-18:00", "timezone": "UTC"},
    "preferences": {
        "voice_enabled": True,
        "notification_style": "voice + popup",
        "agent_personality": "friendly coworker",
    },
    "goals": [],
    "facts": [],  # free-form learned facts
}


class Memory:
    def __init__(self):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(settings.memory_db_path, check_same_thread=False)
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                type TEXT NOT NULL,
                description TEXT NOT NULL,
                result TEXT,
                metadata TEXT
            )"""
        )
        self._conn.commit()

        self._collection = None
        if _HAS_CHROMA:
            try:
                client = chromadb.PersistentClient(path=str(settings.chroma_dir))
                self._collection = client.get_or_create_collection("episodic")
            except Exception as e:
                log.warning("ChromaDB unavailable, falling back to keyword recall: %s", e)

        self.profile = self._load_profile()

    # ---------- Episodic layer ----------

    def remember_event(
        self,
        event_type: str,
        description: str,
        result: str = "",
        metadata: Optional[dict] = None,
    ) -> None:
        ts = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (timestamp, type, description, result, metadata) VALUES (?,?,?,?,?)",
                (ts, event_type, description, result, json.dumps(metadata or {})),
            )
            self._conn.commit()
            row_id = cur.lastrowid
        if self._collection is not None:
            try:
                self._collection.add(
                    ids=[str(row_id)],
                    documents=[f"{event_type}: {description} -> {result}"],
                    metadatas=[{"timestamp": ts, "type": event_type}],
                )
            except Exception as e:
                log.warning("Vector index add failed: %s", e)

    def recall(self, query: str, limit: int = 8) -> list[dict]:
        """Fuzzy recall of past events — vector search if available, else keyword."""
        if self._collection is not None:
            try:
                res = self._collection.query(query_texts=[query], n_results=limit)
                ids = [int(i) for i in res["ids"][0]] if res["ids"] else []
                if ids:
                    marks = ",".join("?" * len(ids))
                    rows = self._conn.execute(
                        f"SELECT timestamp, type, description, result FROM events WHERE id IN ({marks})",
                        ids,
                    ).fetchall()
                    return [self._row_to_dict(r) for r in rows]
            except Exception as e:
                log.warning("Vector recall failed: %s", e)
        like = f"%{query}%"
        rows = self._conn.execute(
            "SELECT timestamp, type, description, result FROM events "
            "WHERE description LIKE ? OR type LIKE ? ORDER BY id DESC LIMIT ?",
            (like, like, limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def events_since(self, hours: float = 24.0, event_type: Optional[str] = None) -> list[dict]:
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat(timespec="seconds")
        if event_type:
            rows = self._conn.execute(
                "SELECT timestamp, type, description, result FROM events "
                "WHERE timestamp >= ? AND type = ? ORDER BY id",
                (cutoff, event_type),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT timestamp, type, description, result FROM events WHERE timestamp >= ? ORDER BY id",
                (cutoff,),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row) -> dict:
        return {"timestamp": row[0], "type": row[1], "description": row[2], "result": row[3]}

    # ---------- Semantic layer ----------

    def _load_profile(self) -> dict:
        path = settings.user_profile_path
        if path.exists():
            try:
                stored = json.loads(path.read_text(encoding="utf-8"))
                merged = json.loads(json.dumps(DEFAULT_PROFILE))
                _deep_merge(merged, stored)
                return merged
            except Exception as e:
                log.error("Corrupt user_profile.json (%s) — starting from defaults", e)
        return json.loads(json.dumps(DEFAULT_PROFILE))

    def save_profile(self) -> None:
        settings.user_profile_path.write_text(
            json.dumps(self.profile, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def update_profile(self, dotted_key: str, value: Any) -> None:
        """update_profile('job_preferences.salary_min', 60000)"""
        node = self.profile
        keys = dotted_key.split(".")
        for k in keys[:-1]:
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        self.save_profile()

    def add_fact(self, fact: str) -> None:
        facts = self.profile.setdefault("facts", [])
        if fact not in facts:
            facts.append(fact)
            self.save_profile()

    def profile_summary(self) -> str:
        """Compact text version of the profile for the system prompt."""
        p = self.profile
        parts = []
        if p.get("name"):
            parts.append(f"Name: {p['name']}")
        if p.get("occupation"):
            parts.append(f"Occupation: {p['occupation']}")
        if p.get("skills"):
            parts.append(f"Skills: {', '.join(p['skills'])}")
        if p.get("writing_style"):
            parts.append(f"Writing style: {p['writing_style']}")
        if p.get("goals"):
            parts.append(f"Goals: {', '.join(p['goals'])}")
        jp = p.get("job_preferences", {})
        if jp.get("roles"):
            parts.append(f"Job preferences: {', '.join(jp['roles'])} in {', '.join(jp.get('locations', []) or ['anywhere'])}")
        ps = p.get("posting_style", {})
        if ps.get("linkedin_tone"):
            parts.append(f"LinkedIn tone: {ps['linkedin_tone']}")
        for fact in p.get("facts", [])[-20:]:
            parts.append(f"Fact: {fact}")
        return "\n".join(parts) if parts else "(nothing known about the user yet)"


def _deep_merge(base: dict, incoming: dict) -> None:
    for k, v in incoming.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


memory = Memory()
