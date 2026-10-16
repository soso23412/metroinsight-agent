import pytest

from metro_agent.evaluation.baselines import baseline_predict
from metro_agent.evaluation.metrics import (
    classification_metrics,
    multilabel_metrics,
    retrieval_recall,
)
from metro_agent.evaluation.review import prepare_review, validate_human_review
from metro_agent.storage.db import Store


def test_metrics_hand_calculable_including_invalid_prediction():
    result = classification_metrics(["a", "a", "b"], ["a", "b", "oops"], ["a", "b"])
    assert result["accuracy"] == pytest.approx(1 / 3)
    assert result["classes"]["a"]["f1"] == pytest.approx(2 / 3)
    assert result["macro_f1"] == pytest.approx(1 / 3)
    assert result["invalid_predictions"] == 1
    multi = multilabel_metrics([{"x", "y"}, {"x"}], [{"x"}, {"y"}], ["x", "y"])
    assert multi["micro_f1"] == pytest.approx(2 / 5)
    assert retrieval_recall({"a", "b"}, ["a", "a", "b"], 2) == 0.5
    assert retrieval_recall(set(), [], 5) is None


def test_duplicate_and_event_groups_do_not_cross_splits(tmp_path, make_content):
    with Store(tmp_path / "d.sqlite3") as store:
        with store.transaction():
            store.add_dataset("d", {})
            contents = [
                make_content(content_id=str(i), text=t)
                for i, t in enumerate(
                    ["地铁非常拥挤！", "地铁非常拥挤", "今天站台突然停电", "同一次停电的另一条记录"]
                )
            ]
            for c in contents:
                store.add_content("d", c)
        review = prepare_review(
            store, "d", event_groups={contents[2].key: "e1", contents[3].key: "e1"}
        )
        rows = review["records"]
        assert rows[0]["group_id"] == rows[1]["group_id"]
        assert rows[2]["group_id"] == rows[3]["group_id"]
        assert rows[2]["split"] == rows[3]["split"]
        assert review["human_gold"] is False
        with pytest.raises(ValueError, match="human_review_required"):
            validate_human_review(review)


def test_tfidf_fits_train_only_and_rejects_group_leak():
    train = [
        {"group_id": "a", "text": "拥挤晚点", "analysis": {"sentiment": "negative"}},
        {"group_id": "b", "text": "准点干净", "analysis": {"sentiment": "positive"}},
    ]
    test = [{"group_id": "c", "text": "晚点火星独角兽"}]
    first = baseline_predict(train, test, "sentiment")
    assert first["tfidf_centroid"] == ["negative"]
    assert (
        baseline_predict(train, [{"group_id": "d", "text": "从未见过的词"}], "sentiment")[
            "vocabulary_size_train_only"
        ]
        == first["vocabulary_size_train_only"]
    )
    with pytest.raises(ValueError, match="split_leakage"):
        baseline_predict(train, [{"group_id": "a", "text": "x"}], "sentiment")
