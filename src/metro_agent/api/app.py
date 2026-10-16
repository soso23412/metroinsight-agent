from __future__ import annotations

import json
import threading
from pathlib import Path
from uuid import uuid4

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from pydantic import Field

from metro_agent.agent.contracts import Limits, Task
from metro_agent.agent.journal import Journal, public_run
from metro_agent.agent.service import execute_task, prepare_demo
from metro_agent.config import ModelConfig
from metro_agent.domain.schemas import Contract
from metro_agent.models.chat import LiveChat
from metro_agent.models.demo import DemoAnnotator
from metro_agent.models.offline import OfflineChat
from metro_agent.storage.db import Store


class RunRequest(Contract):
    question: str = Field(min_length=1, max_length=2000)
    dataset_id: str | None = None
    annotator_version: str = DemoAnnotator.version
    mode: str = "offline"
    limits: Limits = Field(default_factory=Limits)


def create_app(directory: Path, *, db: Path | None = None, allow_live: bool = False) -> FastAPI:
    directory.mkdir(parents=True, exist_ok=True)
    db = db or directory / "datasets.sqlite3"
    default_dataset = prepare_demo(db)
    run_db = directory / "runs.sqlite3"
    gate = threading.Lock()
    app = FastAPI(title="MetroInsight Agent", version="0.2.0")

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        # Rebinding / cross-origin protection for an intentionally unauthenticated localhost app.
        host = request.headers.get("host", "").split(":")[0]
        origin = request.headers.get("origin")
        if host not in {"localhost", "127.0.0.1", "testserver"}:
            return HTMLResponse("Local host required", status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin:
            from urllib.parse import urlsplit

            if urlsplit(origin).netloc != request.headers.get("host"):
                return HTMLResponse("Same origin required", status_code=403)
        if int(request.headers.get("content-length", "0")) > 20_000:
            return HTMLResponse("Request too large", status_code=413)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'"
        )
        return response

    def load(run_id: str) -> dict:
        journal = Journal(run_db)
        try:
            return journal.load(run_id)
        except ValueError:
            raise HTTPException(404, "unknown_run") from None
        finally:
            journal.close()

    def background(task: Task, run_id: str):
        try:
            execute_task(db, directory, task, run_id=run_id)
        except Exception:
            journal = Journal(run_db)
            try:
                state = journal.load(run_id)
                state["status"] = "needs_review"
                from metro_agent.agent.journal import event

                event(state, "worker", "failure_redacted")
                journal.save(state)
            finally:
                journal.close()
        finally:
            gate.release()

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (Path(__file__).parent / "web" / "index.html").read_text(encoding="utf-8")

    @app.get("/app.js")
    def javascript():
        return FileResponse(Path(__file__).parent / "web" / "app.js", media_type="text/javascript")

    @app.get("/health")
    def health():
        return {"status": "ok", "live_enabled": allow_live, "default_mode": "offline"}

    @app.get("/datasets")
    def datasets():
        with Store(db) as store:
            rows = store.conn.execute(
                "SELECT dataset_id,manifest FROM datasets ORDER BY dataset_id"
            ).fetchall()
            return {
                "default_dataset": default_dataset,
                "datasets": [
                    {
                        "dataset_id": r[0],
                        "synthetic": bool(json.loads(r[1]).get("synthetic")),
                        "contents": store.count_contents(r[0]),
                        "annotation_versions": [
                            v[0]
                            for v in store.conn.execute(
                                "SELECT DISTINCT annotator_version FROM annotations WHERE dataset_id=?",
                                (r[0],),
                            )
                        ],
                    }
                    for r in rows
                ],
            }

    @app.post("/runs", status_code=202)
    def submit(
        body: RunRequest,
        background_tasks: BackgroundTasks,
        idempotency_key: str | None = Header(default=None, max_length=120),
    ):
        if body.mode not in {"offline", "live"}:
            raise HTTPException(422, "invalid_mode")
        if body.mode == "live" and not allow_live:
            raise HTTPException(403, "live_disabled_by_operator")
        task = Task(**{**body.model_dump(), "dataset_id": body.dataset_id or default_dataset})
        with Store(db) as store:
            manifest = store.dataset_manifest(task.dataset_id)
            if not manifest:
                raise HTTPException(404, "unknown_dataset")
            if task.mode == "offline" and not manifest.get("synthetic"):
                raise HTTPException(422, "offline_requires_synthetic")
        try:
            model = LiveChat(ModelConfig.from_env()) if task.mode == "live" else OfflineChat()
        except (KeyError, ValueError):
            raise HTTPException(503, "model_not_configured") from None
        journal = Journal(run_db)
        try:
            state = journal.create(task, model.identity, idempotency_key or uuid4().hex)
        except ValueError:
            raise HTTPException(409, "idempotency_conflict") from None
        finally:
            journal.close()
        if state["status"] != "queued":
            return public_run(state)
        if not gate.acquire(blocking=False):
            raise HTTPException(409, "worker_busy_retry_same_idempotency_key")
        background_tasks.add_task(background, task, state["run_id"])
        return public_run(state)

    @app.get("/runs/{run_id}")
    def get_run(run_id: str):
        return public_run(load(run_id))

    @app.get("/runs/{run_id}/events")
    def events(run_id: str, after: int = 0, last_event_id: str | None = Header(default=None)):
        state = load(run_id)
        try:
            cursor = max(after, int(last_event_id or 0))
        except ValueError:
            raise HTTPException(422, "invalid_event_cursor") from None
        # Persisted replay SSE. Client reconnects; no task is re-executed by a read.
        chunks = [
            f"id: {e['seq']}\nevent: trace\ndata: {json.dumps(e, ensure_ascii=False)}\n\n"
            for e in state["events"]
            if e["seq"] > cursor
        ]
        chunks.append(f"event: snapshot\ndata: {json.dumps({'status': state['status']})}\n\n")
        return StreamingResponse(
            iter(chunks), media_type="text/event-stream", headers={"Cache-Control": "no-cache"}
        )

    @app.post("/runs/{run_id}/resume", status_code=202)
    def resume(run_id: str, background_tasks: BackgroundTasks):
        state = load(run_id)
        task = Task.model_validate(state["task"])
        if state["status"] in {"completed", "insufficient_evidence", "stopped"}:
            return public_run(state)
        if task.mode == "live":
            raise HTTPException(409, "live_resume_requires_cli_review")
        if not gate.acquire(blocking=False):
            raise HTTPException(409, "worker_busy")
        background_tasks.add_task(background, task, run_id)
        return public_run(state)

    @app.get("/reports/{run_id}")
    def report(run_id: str):
        value = load(run_id)["report"]
        if value is None:
            raise HTTPException(409, "report_not_ready")
        return value

    return app
