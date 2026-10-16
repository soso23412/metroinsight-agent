from copy import deepcopy

import pytest

from metro_agent.demo import seed_demo
from metro_agent.evaluation.review import apply_review, prepare_review
from metro_agent.models.demo import DemoAnnotator
from metro_agent.storage.db import Store


def reviewed(store, dataset):
    packet = prepare_review(store, dataset)
    for row in packet["records"]:
        content = store.get_content(dataset, row["platform"], row["content_id"])
        # Synthetic human declaration only to test contract; never used as a quality score.
        label = DemoAnnotator().analyze(content).model_dump(mode="json")
        label["label_source"] = "human"
        row.update(
            review_status="human_accepted", reviewer="synthetic-review-fixture", analysis=label
        )
    return packet


def test_review_import_is_versioned_idempotent_and_pending_rejected(tmp_path):
    with Store(tmp_path / "data.sqlite3") as store:
        dataset = seed_demo(store)
        packet = reviewed(store, dataset)
        result = apply_review(store, packet)
        assert result["accepted"] == 12
        assert apply_review(store, packet) == result
        assert store.conn.execute("SELECT count(*) FROM annotations").fetchone()[0] == 12
        pending = deepcopy(packet)
        pending["records"][0]["review_status"] = "pending"
        with pytest.raises(ValueError, match="human_review"):
            apply_review(store, pending)


def test_review_source_tampering_rolls_back_entire_import(tmp_path):
    with Store(tmp_path / "data.sqlite3") as store:
        dataset = seed_demo(store)
        packet = reviewed(store, dataset)
        packet["records"][-1]["content_id"] = "does-not-exist"
        with pytest.raises(ValueError, match="source_mismatch"):
            apply_review(store, packet)
        assert store.conn.execute("SELECT count(*) FROM annotations").fetchone()[0] == 0
