from __future__ import annotations

import json
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

from metro_agent import __version__
from metro_agent.agent.contracts import Task
from metro_agent.agent.service import execute_task, prepare_demo
from metro_agent.agent.tools import ToolBox
from metro_agent.domain.schemas import Relevance, Sentiment
from metro_agent.evaluation.baselines import baseline_predict
from metro_agent.evaluation.metrics import classification_metrics, retrieval_recall
from metro_agent.evaluation.review import validate_human_review
from metro_agent.models.demo import DemoAnnotator
from metro_agent.storage.db import Store


def evaluate_contracts(output: Path) -> dict:
    raw = files("metro_agent.resources").joinpath("contracts.json").read_bytes()
    contracts = json.loads(raw)
    output.mkdir(parents=True, exist_ok=True)
    db = output / "datasets.sqlite3"
    dataset = prepare_demo(db)
    task_results = []
    for case in contracts["tasks"]:
        state = execute_task(
            db,
            output / "runs",
            Task(
                dataset_id=dataset,
                annotator_version=DemoAnnotator.version,
                question=case["question"],
            ),
            idempotency_key=f"{contracts['version']}:{case['id']}",
        )
        report = state["report"]
        checks = {"status": state["status"] == case["status"], "report": report is not None}
        if report:
            checks["number"] = report["metrics"][0]["relevant_denominator"] == case["denominator"]
            for field in ("city", "line"):
                if field in case:
                    checks[field] = all(e[field] == case[field] for e in report["evidence"])
            if case.get("timeline"):
                checks["timeline"] = bool(report["timelines"][0]["items"])
            if case.get("group_by"):
                checks["group_by"] = report["metrics"][0]["group_by"] == case["group_by"]
            checks["evidence"] = bool(report["evidence"]) == (case["status"] == "completed")
        task_results.append(
            {
                "id": case["id"],
                "run_id": state["run_id"],
                "checks": checks,
                "passed": all(checks.values()),
            }
        )
    retrieval = []
    with Store(db) as store:
        toolbox = ToolBox(store, dataset, DemoAnnotator.version)
        texts = {c.content_id: c.text for c in store.iter_contents(dataset)}
        try:
            for case in contracts["retrieval"]:
                got = toolbox.execute("retrieve_evidence", {"query": case["query"], "k": 10}, {})
                ids = [e["content_id"] for e in got["evidence"]]
                baseline = sorted(key for key, text in texts.items() if case["query"] in text)
                expected = set(case["ids"])
                retrieval.append(
                    {
                        "query": case["query"],
                        "expected": case["ids"],
                        "retrieved": ids,
                        "recall_at_5": retrieval_recall(expected, ids, 5),
                        "recall_at_10": retrieval_recall(expected, ids, 10),
                        "substring_recall_at_5": retrieval_recall(expected, baseline, 5),
                        "empty_correct": not ids if not expected else None,
                    }
                )
        finally:
            toolbox.close()
    result = {
        "version": __version__,
        "scope": contracts["kind"],
        "model_calls": 0,
        "contract_sha256": sha256(raw).hexdigest(),
        "dataset_id": dataset,
        "tasks": task_results,
        "task_passed": sum(r["passed"] for r in task_results),
        "task_count": len(task_results),
        "retrieval": retrieval,
        "mean_recall_at_5": sum(r["recall_at_5"] for r in retrieval if r["recall_at_5"] is not None)
        / sum(r["recall_at_5"] is not None for r in retrieval),
        "limits": "Authored synthetic cases known to implementation; NOT real-model accuracy or human blind-test evidence.",
    }
    (output / "evaluation.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return result


def evaluate_review(review_path: Path, output: Path) -> dict:
    raw = review_path.read_bytes()
    rows = validate_human_review(json.loads(raw))
    train, test = (
        [r for r in rows if r["split"] == "train"],
        [r for r in rows if r["split"] == "test"],
    )
    results = {}
    for field, labels in (
        ("relevance", [e.value for e in Relevance]),
        ("sentiment", [e.value for e in Sentiment]),
    ):
        predictions = baseline_predict(train, test, field)
        results[field] = {
            name: classification_metrics(
                [r["analysis"][field] for r in test], predictions[name], labels
            )
            for name in ("majority", "tfidf_centroid")
        }
    result = {
        "review_sha256": sha256(raw).hexdigest(),
        "train_n": len(train),
        "test_n": len(test),
        "scope": "reviewer declarations must be independently audited",
        "results": results,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result
