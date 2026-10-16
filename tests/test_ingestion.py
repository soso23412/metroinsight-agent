import csv
import json
from datetime import timedelta

import pytest

from metro_agent.ingestion.normalize import count, timestamp
from metro_agent.ingestion.service import ingest
from metro_agent.storage.db import Store


@pytest.mark.parametrize(
    ("raw", "expected", "warning"),
    [
        ("1.7万", 17000, None),
        ("1,234", 1234, None),
        (None, None, None),
        ("未知", None, "invalid_count"),
        (-1, None, "invalid_count"),
    ],
)
def test_counts_preserve_missing_and_invalid(raw, expected, warning):
    assert count(raw) == (expected, warning)


def test_seconds_milliseconds_and_shanghai_text_share_timezone():
    a, _ = timestamp(1735689600)
    b, _ = timestamp(1735689600000)
    c, _ = timestamp("2025年01月01日08:00")
    assert a == b == c
    assert a.utcoffset() == timedelta(hours=8)


def test_bad_rows_duplicates_and_id_conflicts_are_accounted(write_jsonl):
    path = write_jsonl(
        [
            {"note_id": "one", "desc": "首条正文", "time": "broken", "liked_count": "unknown"},
            "{broken json",
            {"note_id": "one", "desc": "首条正文"},
            {"note_id": "one", "desc": "不同正文冲突"},
            {"note_id": "", "desc": "空ID"},
            {"note_id": 123456789123456789, "desc": "数字ID不能静默强转"},
            {"note_id": "two", "desc": "第二条仍成功"},
        ]
    )
    with Store(":memory:") as store:
        result = ingest(store, path, kind="xhs")
        stats = result["contents"]
        assert (stats["input_rows"], stats["accepted"], stats["duplicates"], stats["rejected"]) == (
            7,
            2,
            1,
            4,
        )
        assert stats["warning_rows"] == 1
        assert store.count_contents(result["dataset_id"]) == 2
        first = store.get_content(result["dataset_id"], "xhs", "one")
        assert first.published_at is None and first.like_count is None
        assert "invalid_timestamp" in first.warnings
        assert "首条正文" not in json.dumps(stats, ensure_ascii=False)


def test_same_file_is_idempotent_and_changed_file_gets_new_version(write_jsonl):
    path = write_jsonl([{"note_id": "one", "desc": "正文"}])
    with Store(":memory:") as store:
        first = ingest(store, path, kind="xhs")
        repeated = ingest(store, path, kind="xhs")
        assert repeated["reused"] is True
        assert first["dataset_id"] == repeated["dataset_id"]
        path.write_text('{"note_id":"one","desc":"修改内容"}', encoding="utf-8")
        changed = ingest(store, path, kind="xhs")
        assert first["dataset_id"] != changed["dataset_id"]
        assert store.get_content(first["dataset_id"], "xhs", "one").text == "正文"


def test_orphan_comments_rejected_and_profiles_not_collected(write_jsonl):
    path = write_jsonl(
        [
            {
                "note_id": "one",
                "desc": "原文",
                "nickname": "PRIVATE_NAME",
                "note_url": "https://example.com/n/1?xsec_token=PRIVATE_VALUE",
            }
        ]
    )
    comments = write_jsonl(
        [
            {"comment_id": "c1", "note_id": "one", "content": "评论"},
            {"comment_id": "c2", "note_id": "missing", "content": "孤儿评论"},
        ],
        name="comments.jsonl",
    )
    with Store(":memory:") as store:
        result = ingest(store, path, kind="xhs", comments_path=comments)
        assert result["comments"]["accepted"] == 1
        assert result["comments"]["rejected"] == 1
        saved = store.get_content(result["dataset_id"], "xhs", "one")
        assert saved.url == "https://example.com/n/1"
        assert "PRIVATE" not in saved.model_dump_json()


def test_weibo_csv_preserves_first_record_and_warns_lossy_id(tmp_path):
    path = tmp_path / "weibo.csv"
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["微博id", "正文", "时间"])
        writer.writeheader()
        writer.writerow({"微博id": "12345.0", "正文": "地铁很拥挤", "时间": "2023年01月04日00:38"})
    with Store(":memory:") as store:
        result = ingest(store, path, kind="weibo")
        saved = store.get_content(result["dataset_id"], "weibo", "12345.0")
        assert saved.source.row == 2
        assert saved.published_at.utcoffset() == timedelta(hours=8)
        assert saved.warnings == ["possibly_lossy_legacy_id"]


def test_weibo_missing_header_rolls_back_dataset(tmp_path):
    path = tmp_path / "no-header.csv"
    path.write_text("123,这是第一行数据\n456,第二行", encoding="utf-8")
    with Store(":memory:") as store:
        with pytest.raises(ValueError, match="headers"):
            ingest(store, path, kind="weibo")
        assert store.conn.execute("SELECT count(*) FROM datasets").fetchone()[0] == 0


def test_empty_and_media_only_comments_are_explicitly_preserved(write_jsonl):
    path = write_jsonl([{"note_id": "one", "desc": "原文"}])
    comment_path = write_jsonl(
        [
            {
                "comment_id": "media",
                "note_id": "one",
                "content": "",
                "pictures": "https://example.com/image?token=private",
            },
            {"comment_id": "empty", "note_id": "one", "content": "", "pictures": ""},
        ],
        name="comments.jsonl",
    )
    with Store(":memory:") as store:
        result = ingest(store, path, kind="xhs", comments_path=comment_path)
        assert result["comments"]["accepted"] == 2
        assert result["comments"]["warning_rows"] == 2
        rows = [
            json.loads(r[0])
            for r in store.conn.execute("SELECT payload FROM comments ORDER BY comment_id")
        ]
        assert [r["text_status"] for r in rows] == ["empty", "media_only"]
        assert rows[1]["media_count"] == 1
        assert "private" not in json.dumps(rows)
