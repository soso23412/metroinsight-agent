from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from metro_agent import __version__
from metro_agent.agent.contracts import Limits, Task
from metro_agent.agent.journal import Journal
from metro_agent.agent.service import execute_task, prepare_demo
from metro_agent.demo import run_demo
from metro_agent.ingestion.service import ingest
from metro_agent.models.demo import DemoAnnotator
from metro_agent.storage.db import Store


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="MetroInsight reproducible transit feedback baseline"
    )
    parser.add_argument("--version", action="version", version=__version__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run explicitly synthetic, no-key offline demo")
    demo.add_argument("--offline", action="store_true", required=True)
    demo.add_argument("--output", type=Path, default=Path("artifacts/demo"))
    importer = commands.add_parser(
        "ingest", help="Normalize local authorized exports; no model calls"
    )
    importer.add_argument("--contents", type=Path, required=True)
    importer.add_argument("--adapter", choices=["xhs", "weibo"], required=True)
    importer.add_argument("--comments", type=Path)
    importer.add_argument(
        "--db", type=Path, required=True, help="Use a NEW output DB, not old transit.db"
    )
    analyze = commands.add_parser(
        "analyze", help="Run bounded tool agent; offline is synthetic only"
    )
    analyze.add_argument("--question", required=True)
    analyze.add_argument("--mode", choices=["offline", "live"], default="offline")
    analyze.add_argument("--db", type=Path)
    analyze.add_argument("--dataset")
    analyze.add_argument("--annotator-version", default=DemoAnnotator.version)
    analyze.add_argument("--output", type=Path, default=Path("artifacts/agent"))
    analyze.add_argument("--idempotency-key")
    analyze.add_argument("--max-steps", type=int, default=12)
    analyze.add_argument("--max-seconds", type=float, default=180)
    analyze.add_argument("--max-tokens", type=int, default=100000)
    analyze.add_argument("--max-cost-usd", type=float, default=0.1)
    analyze.add_argument("--pause-after", type=int)
    resume = commands.add_parser(
        "resume", help="Resume private checkpoint without repeating completed tools"
    )
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--db", type=Path, required=True)
    resume.add_argument("--output", type=Path, default=Path("artifacts/agent"))
    resume.add_argument(
        "--acknowledge-uncertain",
        action="store_true",
        help="Explicitly accept possible repeat provider charges",
    )
    server = commands.add_parser("serve", help="Launch localhost review UI (single worker)")
    server.add_argument("--output", type=Path, default=Path("artifacts/workbench"))
    server.add_argument("--db", type=Path)
    server.add_argument("--port", type=int, default=8000)
    server.add_argument(
        "--allow-live",
        action="store_true",
        help="Operator opt-in; requires model/prices environment",
    )
    evaluate = commands.add_parser(
        "evaluate", help="Offline synthetic contracts or reviewed human baselines"
    )
    evaluate.add_argument("--output", type=Path, default=Path("artifacts/evaluation"))
    evaluate.add_argument("--review", type=Path)
    review = commands.add_parser(
        "prepare-review", help="Export local pending human review; never auto-create gold labels"
    )
    review.add_argument("--db", type=Path, required=True)
    review.add_argument("--dataset", required=True)
    review.add_argument("--output", type=Path, default=Path("artifacts/review/pending.json"))
    review.add_argument("--event-groups", type=Path)
    review.add_argument("--limit", type=int, default=1000)
    annotate = commands.add_parser(
        "annotate", help="Explicit opt-in paid labeling; default evaluation/demo never calls this"
    )
    annotate.add_argument("--db", type=Path, required=True)
    annotate.add_argument("--dataset", required=True)
    annotate.add_argument("--limit", type=int, default=20)
    annotate.add_argument("--max-cost-usd", type=float, required=True)
    annotate.add_argument("--output", type=Path, default=Path("artifacts/annotation/run.json"))
    apply = commands.add_parser("apply-review", help="Validate and import human-reviewed labels")
    apply.add_argument("--db", type=Path, required=True)
    apply.add_argument("--review", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = run_demo(args.output)
        elif args.command == "serve":
            import uvicorn

            from metro_agent.api.app import create_app

            uvicorn.run(
                create_app(args.output, db=args.db, allow_live=args.allow_live),
                host="127.0.0.1",
                port=args.port,
                access_log=False,
            )
            return 0
        elif args.command == "analyze":
            db = args.db or args.output / "datasets.sqlite3"
            if args.mode == "live" and (args.db is None or not args.dataset):
                raise ValueError("live_requires_explicit_database_and_dataset")
            dataset = args.dataset or prepare_demo(db)
            task = Task(
                dataset_id=dataset,
                annotator_version=args.annotator_version,
                question=args.question,
                mode=args.mode,
                limits=Limits(
                    max_steps=args.max_steps,
                    max_seconds=args.max_seconds,
                    max_tokens=args.max_tokens,
                    max_cost_usd=args.max_cost_usd,
                ),
            )
            result = execute_task(
                db,
                args.output,
                task,
                idempotency_key=args.idempotency_key,
                pause_after=args.pause_after,
            )
        elif args.command == "resume":
            journal = Journal(args.output / "runs.sqlite3")
            try:
                task = Task.model_validate(journal.load(args.run_id)["task"])
            finally:
                journal.close()
            result = execute_task(
                args.db,
                args.output,
                task,
                run_id=args.run_id,
                acknowledge_uncertain=args.acknowledge_uncertain,
            )
        elif args.command == "evaluate":
            from metro_agent.evaluation.runner import evaluate_contracts, evaluate_review

            result = (
                evaluate_review(args.review, args.output / "baselines.json")
                if args.review
                else evaluate_contracts(args.output)
            )
        elif args.command == "prepare-review":
            from metro_agent.evaluation.review import prepare_review

            event_groups = (
                json.loads(args.event_groups.read_text(encoding="utf-8"))
                if args.event_groups
                else None
            )
            with Store(args.db) as store:
                result = prepare_review(
                    store, args.dataset, event_groups=event_groups, limit=args.limit
                )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            result = {
                "output": str(args.output),
                "records": len(result["records"]),
                "human_gold": False,
            }
        elif args.command == "annotate":
            from metro_agent.annotation.live import annotate_live
            from metro_agent.config import ModelConfig
            from metro_agent.models.chat import LiveChat

            with Store(args.db) as store:
                result = annotate_live(
                    store,
                    args.dataset,
                    LiveChat(ModelConfig.from_env()),
                    Limits(max_cost_usd=args.max_cost_usd),
                    args.limit,
                )
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        elif args.command == "apply-review":
            from metro_agent.evaluation.review import apply_review

            with Store(args.db) as store:
                result = apply_review(store, json.loads(args.review.read_text(encoding="utf-8")))
        else:
            with Store(args.db) as store:
                result = ingest(
                    store, args.contents, kind=args.adapter, comments_path=args.comments
                )
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if args.command == "demo" and result["processing"]["failed"]:
            return 1
        if args.command == "ingest" and (
            result["contents"]["rejected"] or result["comments"]["rejected"]
        ):
            return 2
        if args.command in {"analyze", "resume"} and result["status"] not in {
            "completed",
            "insufficient_evidence",
        }:
            return 2
        if (
            args.command == "evaluate"
            and "task_count" in result
            and result["task_passed"] != result["task_count"]
        ):
            return 2
        if args.command == "annotate" and (result["failed"] or result["stop_reason"]):
            return 2
        return 0
    except (ValueError, OSError, KeyError, sqlite3.Error) as exc:
        # No raw data row, URL query or credentials are printed on failures.
        print(
            f"Operation failed ({type(exc).__name__}); check input format and output DB.",
            file=sys.stderr,
        )
        return 1
