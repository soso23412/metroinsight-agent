import json

import pytest

from metro_agent.agent.contracts import Call, Decision, Limits, Task
from metro_agent.agent.graph import run_agent
from metro_agent.agent.journal import Journal
from metro_agent.agent.service import prepare_demo
from metro_agent.models.chat import ModelFailure
from metro_agent.models.demo import DemoAnnotator
from metro_agent.models.offline import OfflineChat
from metro_agent.storage.db import Store


@pytest.fixture
def env(tmp_path):
    db = tmp_path / "data.sqlite3"
    dataset = prepare_demo(db)
    store = Store(db)
    journal = Journal(tmp_path / "runs.sqlite3")
    task = Task(
        dataset_id=dataset,
        annotator_version=DemoAnnotator.version,
        question="分析示例1号线服务反馈",
    )
    yield store, journal, task
    store.close()
    journal.close()


def execute(env, model=None, **kwargs):
    store, journal, task = env
    model = model or OfflineChat()
    state = journal.create(task, model.identity)
    return run_agent(journal, store, state["run_id"], model, **kwargs)


def test_loop_metrics_and_citations_are_observed(env):
    state = execute(env)
    assert state["status"] == "completed"
    metric = state["report"]["metrics"][0]
    assert metric["relevant_denominator"] == 5
    assert {r["label"]: r["count"] for r in metric["groups"]} == {"negative": 3, "neutral": 2}
    assert len(state["report"]["evidence"]) == 5
    assert all(e["line"] == "示例1号线" for e in state["report"]["evidence"])
    assert state["reserved_cost_usd"] == 0


def test_resume_does_not_repeat_tools(env):
    store, journal, task = env
    first = execute(env, pause_after=2)
    assert first["status"] == "paused" and len(first["receipts"]) == 2
    journal.close()
    reopened = Journal(
        journal_path := __import__("pathlib").Path(store.path).parent / "runs.sqlite3"
    )
    try:
        final = run_agent(reopened, store, first["run_id"], OfflineChat())
        assert final["status"] == "completed"
        assert len([e for e in final["events"] if e.get("tool") == "aggregate_feedback"]) == 1
        assert journal_path.exists()
    finally:
        reopened.close()


def test_idempotency_conflict_and_final_replay(env):
    store, journal, task = env
    first = journal.create(task, OfflineChat.identity, "same")
    again = journal.create(task, OfflineChat.identity, "same")
    assert first["run_id"] == again["run_id"]
    with pytest.raises(ValueError, match="idempotency_conflict"):
        journal.create(
            task.model_copy(update={"question": "不同任务"}), OfflineChat.identity, "same"
        )
    end = run_agent(journal, store, first["run_id"], OfflineChat())
    assert run_agent(journal, store, first["run_id"], OfflineChat())["events"] == end["events"]


def test_no_evidence_returns_explicit_limitation(env):
    env[2].question = "分析示例999号线服务反馈"
    state = execute(env)
    assert state["status"] == "insufficient_evidence"
    assert state["report"]["evidence"] == []
    assert state["report"]["metrics"][0]["relevant_denominator"] == 0


class InvalidTool(OfflineChat):
    def decide(self, messages, timeout):
        return Decision(
            calls=[Call(id="bad", name="run_shell", arguments={"command": "echo unsafe"})]
        )


def test_unknown_tool_cannot_execute_and_loop_is_bounded(env):
    env[2].limits.max_steps = 3
    state = execute(env, InvalidTool())
    assert state["status"] == "stopped" and state["steps"] == 3
    assert all(not r["ok"] for r in state["receipts"].values())
    assert state["events"][-1]["status"] == "step_limit"


class ForgedFinish(OfflineChat):
    def decide(self, messages, timeout):
        return Decision(
            calls=[
                Call(
                    id="bad",
                    name="finish_report",
                    arguments={
                        "status": "completed",
                        "evidence_ids": ["forged"],
                        "metric_result_ids": ["fake"],
                    },
                )
            ]
        )


def test_forged_report_cannot_be_published(env):
    env[2].limits.max_steps = 2
    state = execute(env, ForgedFinish())
    assert state["report"] is None
    assert all(not r["ok"] for r in state["receipts"].values())


@pytest.mark.parametrize(
    ("limit", "reason"),
    [
        (Limits(max_tokens=1), "token_limit"),
        (Limits(max_cost_usd=0), "cost_limit"),
        (Limits(max_seconds=0.000001), "time_limit"),
    ],
)
def test_resource_preflight_prevents_model_request(env, limit, reason):
    class Reserved(OfflineChat):
        def reserve(self, messages):
            return 100, 0.01

        def decide(self, messages, timeout):
            pytest.fail("request must be prevented")

    env[2].limits = limit
    model = Reserved()
    state = env[1].create(env[2], model.identity)
    if reason == "time_limit":
        state["elapsed"] = limit.max_seconds + 1
        env[1].save(state)
    state = run_agent(env[1], env[0], state["run_id"], model)
    assert state["status"] == "stopped" and state["events"][-1]["status"] == reason


def test_uncertain_request_not_automatically_repeated(env):
    class Timeout(OfflineChat):
        def decide(self, messages, timeout):
            raise ModelFailure("provider_network_uncertain", uncertain=True)

    state = execute(env, Timeout())
    assert state["status"] == "needs_review"
    resumed = run_agent(env[1], env[0], state["run_id"], OfflineChat())
    assert resumed["steps"] == 1 and resumed["status"] == "needs_review"
    final = run_agent(env[1], env[0], state["run_id"], OfflineChat(), acknowledge_uncertain=True)
    assert final["status"] == "completed"


def test_changed_data_or_model_cannot_resume(env):
    state = execute(env, pause_after=1)

    class Changed(OfflineChat):
        identity = "another-model"

    with pytest.raises(ValueError, match="configuration_mismatch"):
        run_agent(env[1], env[0], state["run_id"], Changed())
    env[0].conn.execute("UPDATE annotations SET status='failed'")
    env[0].conn.commit()
    with pytest.raises(ValueError, match="checkpoint_data_changed"):
        run_agent(env[1], env[0], state["run_id"], OfflineChat())


def test_prompt_injection_stays_data_and_trace_is_redacted(env):
    # Tool returns untrusted data, but a malicious policy still cannot gain new privileges.
    state = execute(env, InvalidTool())
    trace = json.dumps(state["events"])
    assert "echo unsafe" not in trace
    assert "question" not in trace


def test_lease_rejects_concurrent_execution(env):
    state = env[1].create(env[2], OfflineChat.identity)
    env[1].acquire(state["run_id"], 10)
    with pytest.raises(ValueError, match="already_running"):
        run_agent(env[1], env[0], state["run_id"], OfflineChat())
    env[1].release(state["run_id"])


def test_event_timeline_is_in_final_report(env):
    env[2].question = "梳理故障事件候选的时间线"
    state = execute(env)
    assert state["report"]["timelines"][0]["items"][0]["content_id"] == "demo-07"
    assert state["report"]["timelines"][0]["items"][0]["verification"] == "unverified"
