from metro_agent.annotation.pipeline import process
from metro_agent.models.demo import DemoAnnotator
from metro_agent.storage.db import Store


class SometimesInvalid:
    version = DemoAnnotator.version

    def analyze(self, content):
        if content.content_id == "bad":
            return {"relevance": "invented"}
        return DemoAnnotator().analyze(content)


def test_partial_failure_is_visible_and_successes_not_reprocessed(make_content):
    with Store(":memory:") as store:
        with store.transaction():
            store.add_dataset("test", {})
            store.add_content("test", make_content(content_id="bad"))
            store.add_content("test", make_content(content_id="ok"))
        first = process(store, "test", SometimesInvalid())
        assert first["succeeded"] == 1 and first["failed"] == 1
        row = store.conn.execute(
            "SELECT status,payload FROM annotations WHERE content_id='bad'"
        ).fetchone()
        assert tuple(row) == ("failed", None)
        rerun = process(store, "test", DemoAnnotator())
        assert rerun["attempted"] == 1 and rerun["cached"] == 1 and rerun["succeeded"] == 1
        assert store.conn.execute("SELECT count(*) FROM annotations").fetchone()[0] == 2


def test_changed_annotator_version_does_not_reuse_old_results(make_content):
    class NewVersion:
        version = "synthetic-rules:demo-v2:1"

        def analyze(self, content):
            result = DemoAnnotator().analyze(content)
            result.prompt_version = "demo-v2"
            return result

    with Store(":memory:") as store:
        with store.transaction():
            store.add_dataset("test", {})
            store.add_content("test", make_content())
        process(store, "test", DemoAnnotator())
        updated = process(store, "test", NewVersion())
        assert updated["attempted"] == 1 and updated["cached"] == 0
        assert store.conn.execute("SELECT count(*) FROM annotations").fetchone()[0] == 2
