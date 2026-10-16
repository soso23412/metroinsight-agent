from __future__ import annotations

from pathlib import Path

from metro_agent.agent.contracts import Task
from metro_agent.agent.graph import run_agent
from metro_agent.agent.journal import Journal, public_run
from metro_agent.annotation.pipeline import process
from metro_agent.config import ModelConfig
from metro_agent.demo import seed_demo
from metro_agent.models.chat import LiveChat
from metro_agent.models.demo import DemoAnnotator
from metro_agent.models.offline import OfflineChat
from metro_agent.reporting.agent_report import write_agent_report
from metro_agent.storage.db import Store


def prepare_demo(db: Path) -> str:
    with Store(db) as store:
        dataset = seed_demo(store)
        process(store, dataset, DemoAnnotator())
        return dataset


def execute_task(
    db: Path,
    directory: Path,
    task: Task,
    *,
    idempotency_key: str | None = None,
    run_id: str | None = None,
    pause_after: int | None = None,
    acknowledge_uncertain: bool = False,
) -> dict:
    model = LiveChat(ModelConfig.from_env()) if task.mode == "live" else OfflineChat()
    journal = Journal(directory / "runs.sqlite3")
    try:
        with Store(db) as store:
            state = (
                journal.load(run_id)
                if run_id
                else journal.create(task, model.identity, idempotency_key)
            )
            state = run_agent(
                journal,
                store,
                state["run_id"],
                model,
                pause_after=pause_after,
                acknowledge_uncertain=acknowledge_uncertain,
            )
        write_agent_report(state, directory / state["run_id"])
        return public_run(state)
    finally:
        journal.close()
