import hashlib
import sqlite3

import pytest

from metro_agent.models.demo import DemoAnnotator
from metro_agent.storage.db import Store


def test_platforms_and_datasets_isolate_same_original_id(make_content):
    with Store(":memory:") as store, store.transaction():
        store.add_dataset("a", {})
        store.add_dataset("b", {})
        xhs = make_content(platform="xhs")
        weibo = make_content(platform="weibo")
        assert store.add_content("a", xhs) == "inserted"
        assert store.add_content("a", weibo) == "inserted"
        assert store.add_content("b", xhs) == "inserted"
        assert store.count_contents("a") == 2
        assert store.count_contents("b") == 1
        assert store.add_content("a", xhs) == "duplicate"


def test_refuses_to_modify_historical_or_other_database(tmp_path):
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE contents(content_id TEXT)")
        conn.execute("INSERT INTO contents VALUES ('original')")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="unrecognized"):
        Store(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_transaction_rolls_back_partial_import(make_content):
    with Store(":memory:") as store:
        with pytest.raises(RuntimeError), store.transaction():
            store.add_dataset("a", {})
            store.add_content("a", make_content())
            raise RuntimeError("interrupt")
        assert store.dataset_manifest("a") is None
        assert store.count_contents("a") == 0


def test_invalid_evidence_is_not_written(make_content):
    with Store(":memory:") as store, store.transaction():
        content = make_content()
        store.add_dataset("a", {})
        store.add_content("a", content)
        analysis = DemoAnnotator().analyze(content)
        analysis.evidence = []
        with pytest.raises(ValueError, match="evidence"):
            store.save_analysis("a", content, analysis)
        assert store.conn.execute("SELECT count(*) FROM annotations").fetchone()[0] == 0
