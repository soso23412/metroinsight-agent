import pytest

from metro_agent.agent.service import prepare_demo
from metro_agent.agent.tools import ToolBox
from metro_agent.retrieval.index import tokens
from metro_agent.storage.db import Store


@pytest.fixture
def box(tmp_path):
    db = tmp_path / "data.sqlite3"
    dataset = prepare_demo(db)
    with Store(db) as store:
        toolbox = ToolBox(store, dataset, "synthetic-rules:demo-v1:1")
        yield toolbox
        toolbox.close()


@pytest.mark.parametrize(
    "args",
    [
        {"dataset_id": "another"},
        {"sql": "DROP TABLE contents"},
        {"group_by": "author"},
        {"city": "a", "path": "../secret"},
        {"start": "2026-99-99"},
    ],
)
def test_tool_schema_rejects_escalation(box, args):
    with pytest.raises(ValueError):
        box.execute("aggregate_feedback", args, {})


def test_counts_filters_dates_and_overlapping_aspects(box):
    result = box.execute("aggregate_feedback", {"group_by": "aspect"}, {})
    assert result["relevant_denominator"] == 10
    assert sum(r["count"] for r in result["groups"]) > 10
    assert result["overlapping"]
    narrowed = box.execute("aggregate_feedback", {"start": "2026-01-06", "end": "2026-01-06"}, {})
    assert narrowed["annotated_total"] == 4 and narrowed["relevant_denominator"] == 2
    attack = box.execute("aggregate_feedback", {"city": "' OR 1=1 --"}, {})
    assert attack["relevant_denominator"] == 0


def test_chinese_retrieval_filters_before_topk(box):
    found = box.execute("retrieve_evidence", {"query": "拥挤", "line": "示例2号线", "k": 1}, {})
    assert found["evidence"][0]["content_id"] == "demo-04"
    assert "拥挤" in tokens("线路拥挤")
    assert box.execute("retrieve_evidence", {"query": "火星独角兽"}, {})["empty"]
    assert box.execute("retrieve_evidence", {"query": '" OR * NEAR()'}, {})["empty"]


def test_cannot_read_unobserved_or_other_dataset_evidence(box):
    with pytest.raises(ValueError, match="not_visible"):
        box.execute("read_evidence", {"evidence_ids": ["not-in-this-run"]}, {})
    sample = box.execute("retrieve_evidence", {"query": "晚点"}, {})["evidence"][0]
    found = box.execute(
        "read_evidence", {"evidence_ids": [sample["evidence_id"]]}, {sample["evidence_id"]: sample}
    )
    assert found["evidence"][0]["quote"] == sample["quote"]
