from __future__ import annotations

import json
import re
import unicodedata
from hashlib import sha256

from metro_agent.domain.schemas import Analysis
from metro_agent.storage.db import Store


def normalized(text: str) -> str:
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text).lower())


def prepare_review(
    store: Store, dataset_id: str, *, event_groups: dict[str, str] | None = None, limit: int = 1000
) -> dict:
    if not 1 <= limit <= 2000:
        raise ValueError("review_limit_1_to_2000")
    contents = []
    for c in store.iter_contents(dataset_id):
        contents.append(c)
        if len(contents) > limit:
            raise ValueError("review_subset_required_no_silent_truncation")
    if not contents:
        raise ValueError("empty_review_dataset")
    event_groups = event_groups or {}
    parents = list(range(len(contents)))

    def root(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i

    texts = [normalized(c.text) for c in contents]
    shingles = [{t[i : i + 2] for i in range(len(t) - 1)} for t in texts]
    for i in range(len(contents)):
        for j in range(i):
            event_i, event_j = event_groups.get(contents[i].key), event_groups.get(contents[j].key)
            union = shingles[i] | shingles[j]
            similarity = len(shingles[i] & shingles[j]) / len(union) if union else 0
            if texts[i] == texts[j] or similarity >= 0.85 or (event_i and event_i == event_j):
                parents[root(i)] = root(j)
    members = {}
    for i, c in enumerate(contents):
        members.setdefault(root(i), []).append(c.key)
    group_ids = {
        r: sha256("\0".join(sorted(keys)).encode()).hexdigest() for r, keys in members.items()
    }
    records = []
    for i, c in enumerate(contents):
        group = group_ids[root(i)]
        split = (
            "train"
            if int(group[:8], 16) % 10 < 6
            else "dev"
            if int(group[:8], 16) % 10 < 8
            else "test"
        )
        # Previously used XHS development samples may never enter a new blind test.
        if any(contents[j].platform == "xhs" for j in range(len(contents)) if root(j) == root(i)):
            split = "historical_dev"
        records.append(
            {
                "content_key": c.key,
                "platform": c.platform,
                "content_id": c.content_id,
                "text": c.text,
                "text_sha256": c.text_sha256,
                "group_id": group,
                "event_group": event_groups.get(c.key),
                "split": split,
                "review_status": "pending",
                "reviewer": None,
                "analysis": None,
            }
        )
    body = {
        "schema_version": "review-v1",
        "dataset_id": dataset_id,
        "records": records,
        "human_gold": False,
        "split_policy": "group-hash-60/20/20; XHS=historical_dev",
        "warnings": [
            "事件组必须人工补充后重新导出；未分组不能声称事件隔离。",
            "不自动将旧0或C1-C9转为人工真值。没有时间切分，不声称时间外推。",
        ],
    }
    body["manifest_sha256"] = sha256(
        json.dumps(records, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    return body


def validate_human_review(review: dict) -> list[dict]:
    if review.get("schema_version") != "review-v1":
        raise ValueError("unsupported_review_schema")
    valid = []
    group_splits = {}
    seen = set()
    for record in review["records"]:
        if record["review_status"] != "human_accepted" or not record.get("reviewer"):
            raise ValueError("human_review_required")
        if record["content_key"] in seen:
            raise ValueError("duplicate_review_record")
        seen.add(record["content_key"])
        if sha256(record["text"].encode()).hexdigest() != record["text_sha256"]:
            raise ValueError("review_text_changed")
        analysis = Analysis.model_validate(record["analysis"])
        if analysis.label_source != "human":
            raise ValueError("human_reference_cannot_be_prediction")
        if analysis.relevance == "relevant" and not analysis.evidence:
            raise ValueError("review_evidence_required")
        for span in analysis.evidence:
            if record["text"][span.start : span.end] != span.quote:
                raise ValueError("review_evidence_mismatch")
        key = record["group_id"]
        if key in group_splits and group_splits[key] != record["split"]:
            raise ValueError("group_split_leakage")
        group_splits[key] = record["split"]
        valid.append(record)
    if not valid:
        raise ValueError("empty_review")
    return valid


def apply_review(store: Store, review: dict) -> dict:
    rows = validate_human_review(review)
    dataset = review["dataset_id"]
    if store.dataset_manifest(dataset) is None:
        raise ValueError("unknown_review_dataset")
    digest = sha256(json.dumps(review, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    annotator, prompt = "human-review-" + digest[:20], "annotation-guide-v1"
    with store.transaction():
        for row in rows:
            content = store.get_content(dataset, row["platform"], row["content_id"])
            if (
                content is None
                or content.key != row["content_key"]
                or content.text_sha256 != row["text_sha256"]
            ):
                raise ValueError("review_source_mismatch")
            analysis = Analysis.model_validate(row["analysis"]).model_copy(
                update={
                    "annotator": annotator,
                    "prompt_version": prompt,
                }
            )
            store.save_analysis(dataset, content, analysis)
    return {
        "dataset_id": dataset,
        "annotator_version": f"{annotator}:{prompt}:1",
        "accepted": len(rows),
        "review_sha256": digest,
        "model_calls": 0,
    }
