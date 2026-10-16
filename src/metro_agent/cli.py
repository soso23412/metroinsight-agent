from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from metro_agent import __version__
from metro_agent.demo import run_demo
from metro_agent.ingestion.service import ingest
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
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = run_demo(args.output)
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
        return 0
    except (ValueError, OSError) as exc:
        # No raw data row, URL query or credentials are printed on failures.
        print(
            f"Operation failed ({type(exc).__name__}); check input format and output DB.",
            file=sys.stderr,
        )
        return 1
