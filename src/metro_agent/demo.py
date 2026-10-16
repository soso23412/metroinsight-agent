from __future__ import annotations

import json
from hashlib import sha256
from importlib.resources import files
from pathlib import Path

from metro_agent.annotation.pipeline import process
from metro_agent.domain.schemas import Content, SourceRef
from metro_agent.models.demo import DemoAnnotator
from metro_agent.reporting.render import build_report, write_report
from metro_agent.storage.db import Store


def seed_demo(store: Store) -> str:
    raw = files("metro_agent.resources").joinpath("demo.json").read_bytes()
    checksum = sha256(raw).hexdigest()
    dataset_id = f"demo-{checksum[:20]}"
    if store.dataset_manifest(dataset_id) is None:
        with store.transaction():
            store.add_dataset(
                dataset_id,
                {
                    "dataset_id": dataset_id,
                    "synthetic": True,
                    "fixture_sha256": checksum,
                    "description": "Explicitly synthetic teaching data; no real people or incidents.",
                },
            )
            for row, item in enumerate(json.loads(raw), 1):
                store.add_content(
                    dataset_id,
                    Content(
                        **item,
                        synthetic=True,
                        source=SourceRef(source_sha256=checksum, source_name="demo.json", row=row),
                    ),
                )
    return dataset_id


def run_demo(output: Path) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    with Store(output / "demo.sqlite3") as store:
        dataset_id = seed_demo(store)
        annotator = DemoAnnotator()
        processing = process(store, dataset_id, annotator)
        report = build_report(store, dataset_id, annotator.version)
        report["processing"] = processing
        write_report(report, output)
    return {
        "mode": "offline_synthetic",
        "dataset_id": dataset_id,
        "content_count": report["total_contents"],
        "processing": processing,
        "model_calls": 0,
        "report": str((output / "report.html").resolve()),
    }
