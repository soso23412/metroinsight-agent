from __future__ import annotations

import json
import sqlite3
import time
from hashlib import sha256
from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from metro_agent.agent.contracts import Call, FinishArgs, Task
from metro_agent.agent.journal import Journal, event
from metro_agent.agent.tools import ToolBox
from metro_agent.models.chat import ChatModel, ModelFailure
from metro_agent.reporting.agent_report import verify_report
from metro_agent.storage.db import Store


class GraphState(TypedDict):
    record: dict


def run_agent(
    journal: Journal,
    store: Store,
    run_id: str,
    model: ChatModel,
    *,
    pause_after: int | None = None,
    acknowledge_uncertain: bool = False,
) -> dict:
    state = journal.load(run_id)
    task = Task.model_validate(state["task"])
    if state["model"] != model.identity or (task.mode == "live") != model.live:
        raise ValueError("resume_model_configuration_mismatch")
    manifest = store.dataset_manifest(task.dataset_id)
    if not manifest:
        raise ValueError("unknown_dataset")
    if not model.live and not manifest.get("synthetic"):
        raise ValueError("offline_policy_requires_synthetic_dataset")
    if state["status"] in ("completed", "insufficient_evidence", "stopped"):
        return state
    journal.acquire(run_id, task.limits.max_seconds)
    toolbox = None
    start = time.monotonic()
    elapsed_before = state["elapsed"]

    def persist() -> None:
        state["elapsed"] = elapsed_before + time.monotonic() - start
        journal.save(state)

    def stop(code: str) -> None:
        state["status"] = "stopped"
        event(state, "policy", code)
        persist()

    def remaining() -> float:
        return task.limits.max_seconds - elapsed_before - (time.monotonic() - start)

    try:
        snapshot_hash = sha256()
        for row in store.conn.execute(
            "SELECT c.platform,c.content_id,c.payload,a.status,a.payload FROM contents c "
            "LEFT JOIN annotations a ON c.dataset_id=a.dataset_id AND c.platform=a.platform "
            "AND c.content_id=a.content_id AND a.annotator_version=? WHERE c.dataset_id=? "
            "ORDER BY c.platform,c.content_id",
            (task.annotator_version, task.dataset_id),
        ):
            snapshot_hash.update(json.dumps(tuple(row), ensure_ascii=False).encode())
        snapshot = snapshot_hash.hexdigest()
        if state.get("data_snapshot") and state["data_snapshot"] != snapshot:
            raise ValueError("checkpoint_data_changed")
        state["data_snapshot"] = snapshot
        if state["pending"] and state["pending"]["kind"] == "model_request":
            if not acknowledge_uncertain:
                state["status"] = "needs_review"
                event(state, "model", "uncertain_request_not_repeated")
                persist()
                return state
            event(state, "model", "user_acknowledged_possible_repeat_charge")
            state["pending"] = None  # Previous reservation is deliberately not refunded.
        toolbox = ToolBox(store, task.dataset_id, task.annotator_version)
        state["status"] = "running"
        persist()

        def decide(_: GraphState) -> GraphState:
            if remaining() <= 0:
                stop("time_limit")
                return {"record": state}
            if state["pending"]:
                return {"record": state}
            if pause_after is not None and state["steps"] >= pause_after:
                state["status"] = "paused"
                event(state, "checkpoint", "paused")
                persist()
                return {"record": state}
            if state["steps"] >= task.limits.max_steps:
                stop("step_limit")
                return {"record": state}
            reserved_tokens, reserved_usd = model.reserve(state["messages"])
            if state["reserved_tokens"] + reserved_tokens > task.limits.max_tokens:
                stop("token_limit")
                return {"record": state}
            if state["reserved_cost_usd"] + reserved_usd > task.limits.max_cost_usd:
                stop("cost_limit")
                return {"record": state}
            state["reserved_tokens"] += reserved_tokens
            state["reserved_cost_usd"] += reserved_usd
            state["steps"] += 1
            state["pending"] = {"kind": "model_request", "step": state["steps"]}
            event(state, "model", "started", step=state["steps"], model=model.identity)
            persist()  # A crash after send must never silently repeat a billable request.
            if remaining() <= 0:
                state["pending"] = None  # No request has been dispatched.
                stop("time_limit")
                return {"record": state}
            try:
                decision = model.decide(state["messages"], min(30, remaining()))
            except ModelFailure as exc:
                state["status"] = "needs_review" if exc.uncertain else "paused"
                if not exc.uncertain:
                    state["pending"] = None
                event(state, "model", exc.code)
                persist()
                return {"record": state}
            except Exception:
                state["status"] = "needs_review"
                event(state, "model", "unexpected_failure_redacted")
                persist()
                return {"record": state}
            state["usage"].append(
                {
                    "step": state["steps"],
                    "input_tokens": decision.input_tokens,
                    "output_tokens": decision.output_tokens,
                    "source": "provider" if model.live else "synthetic_no_model",
                    "billing": "reservation_estimate_not_invoice",
                }
            )
            state["messages"].append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {
                                "name": c.name,
                                "arguments": json.dumps(c.arguments, ensure_ascii=False),
                            },
                        }
                        for c in decision.calls
                    ],
                }
            )
            state["pending"] = {
                "kind": "tools",
                "calls": [c.model_dump() for c in decision.calls],
                "next": 0,
            }
            event(state, "model", "completed", calls=len(decision.calls))
            persist()
            return {"record": state}

        def tools(_: GraphState) -> GraphState:
            pending = state["pending"]
            for i in range(pending["next"], len(pending["calls"])):
                if remaining() <= 0:
                    stop("time_limit")
                    return {"record": state}
                call = Call.model_validate(pending["calls"][i])
                result_id = f"r{state['steps']}-{i}"
                started = time.monotonic()
                # Only hashes of args appear in portable trace, never private query text.
                args_hash = sha256(json.dumps(call.arguments, sort_keys=True).encode()).hexdigest()
                try:
                    if call.name == "finish_report":
                        if len(pending["calls"]) != 1:
                            raise ValueError("finish_must_be_only_call")
                        report = verify_report(
                            FinishArgs.model_validate(call.arguments), state, store
                        )
                        state["report"], state["status"] = report, report["status"]
                        data = {"validated": True, "status": report["status"]}
                    else:
                        store.conn.set_progress_handler(lambda: int(remaining() <= 0), 1000)
                        try:
                            data = toolbox.execute(call.name, call.arguments, state["visible"])
                        finally:
                            store.conn.set_progress_handler(None, 0)
                    receipt = {"tool": call.name, "result_id": result_id, "ok": True, "data": data}
                    for e in data.get("evidence", []):
                        state["visible"][e["evidence_id"]] = e
                except (ValueError, ValidationError, sqlite3.Error):
                    receipt = {
                        "tool": call.name,
                        "result_id": result_id,
                        "ok": False,
                        "error": "invalid_tool_arguments_or_evidence",
                    }
                state["receipts"][result_id] = receipt
                state["messages"].append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(receipt, ensure_ascii=False),
                    }
                )
                pending["next"] = i + 1
                event(
                    state,
                    "tool",
                    "success" if receipt["ok"] else "rejected",
                    tool=call.name,
                    result_id=result_id,
                    arguments_sha256=args_hash,
                    duration_ms=round((time.monotonic() - started) * 1000, 2),
                )
                persist()
            state["pending"] = None
            persist()
            return {"record": state}

        graph = StateGraph(GraphState)
        graph.add_node("model", decide)
        graph.add_node("tools", tools)
        graph.add_edge(START, "model")
        graph.add_conditional_edges(
            "model", lambda _: "tools" if state["status"] == "running" and state["pending"] else END
        )
        graph.add_conditional_edges(
            "tools", lambda _: "model" if state["status"] == "running" else END
        )
        graph.compile().invoke(
            {"record": state}, {"recursion_limit": task.limits.max_steps * 2 + 5}
        )
        return state
    finally:
        persist()
        if toolbox:
            toolbox.close()
        journal.release(run_id)
