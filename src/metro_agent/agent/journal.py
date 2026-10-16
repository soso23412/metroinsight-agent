from __future__ import annotations

import json
import sqlite3
import time
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from metro_agent.agent.contracts import Task
from metro_agent.models.chat import PROMPT_VERSION, SYSTEM_PROMPT


class Journal:
    """Private checkpoints contain task text; public event summaries never contain it."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=10)
        names = {
            r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if names and "agent_meta" not in names:
            self.conn.close()
            raise ValueError("unrecognized_run_database")
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS agent_meta(version INTEGER NOT NULL);
            CREATE TABLE IF NOT EXISTS runs(
              run_id TEXT PRIMARY KEY, idem TEXT UNIQUE NOT NULL,
              fingerprint TEXT NOT NULL, state TEXT NOT NULL,
              lease_until REAL NOT NULL DEFAULT 0);
        """)
        if not self.conn.execute("SELECT 1 FROM agent_meta").fetchone():
            self.conn.execute("INSERT INTO agent_meta VALUES (1)")
        if self.conn.execute("SELECT version FROM agent_meta").fetchone()[0] != 1:
            raise ValueError("unsupported_run_schema")
        self.conn.commit()

    def create(self, task: Task, identity: str, idempotency_key: str | None = None) -> dict:
        payload = {
            "task": task.model_dump(mode="json"),
            "model": identity,
            "prompt": PROMPT_VERSION,
        }
        fingerprint = sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
        idem = idempotency_key or uuid4().hex
        state = {
            "run_id": uuid4().hex,
            **payload,
            "status": "queued",
            "steps": 0,
            "reserved_tokens": 0,
            "reserved_cost_usd": 0.0,
            "elapsed": 0.0,
            "usage": [],
            "pending": None,
            "receipts": {},
            "visible": {},
            "events": [],
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": task.question},
            ],
            "report": None,
        }
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO runs VALUES (?,?,?,?,0)",
                (state["run_id"], idem, fingerprint, json.dumps(state, ensure_ascii=False)),
            )
            prior = self.conn.execute(
                "SELECT fingerprint,state FROM runs WHERE idem=?", (idem,)
            ).fetchone()
            if prior:
                if prior[0] != fingerprint:
                    raise ValueError("idempotency_conflict")
                return json.loads(prior[1])
        return state

    def load(self, run_id: str) -> dict:
        row = self.conn.execute("SELECT state FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise ValueError("unknown_run")
        return json.loads(row[0])

    def save(self, state: dict) -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE runs SET state=? WHERE run_id=?",
                (json.dumps(state, ensure_ascii=False), state["run_id"]),
            )

    def acquire(self, run_id: str, seconds: float) -> None:
        with self.conn:
            updated = self.conn.execute(
                "UPDATE runs SET lease_until=? WHERE run_id=? AND lease_until<?",
                (time.time() + seconds + 10, run_id, time.time()),
            ).rowcount
        if not updated:
            raise ValueError("run_already_running_or_lease_not_expired")

    def release(self, run_id: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE runs SET lease_until=0 WHERE run_id=?", (run_id,))

    def close(self) -> None:
        self.conn.close()


def event(state: dict, stage: str, status: str, **metadata: object) -> None:
    state["events"].append(
        {"seq": len(state["events"]) + 1, "stage": stage, "status": status, **metadata}
    )


def public_run(state: dict) -> dict:
    return {
        k: state[k]
        for k in (
            "run_id",
            "status",
            "steps",
            "reserved_tokens",
            "reserved_cost_usd",
            "elapsed",
            "usage",
            "events",
            "report",
        )
    }
