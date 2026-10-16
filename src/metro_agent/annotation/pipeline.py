from __future__ import annotations

from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import ValidationError

from metro_agent.domain.schemas import Analysis
from metro_agent.models.base import Annotator
from metro_agent.storage.db import Store


class PipelineState(TypedDict):
    dataset_id: str
    stats: dict


def process(store: Store, dataset_id: str, annotator: Annotator) -> dict:
    if store.dataset_manifest(dataset_id) is None:
        raise ValueError("unknown_dataset")

    def annotate(state: PipelineState) -> dict:
        stats = {"attempted": 0, "succeeded": 0, "cached": 0, "failed": 0, "errors": []}
        # No batch-level list: a million-row import need not fit into model memory.
        for content in store.iter_contents(state["dataset_id"]):
            if store.annotation(dataset_id, content, annotator.version) is not None:
                stats["cached"] += 1
                continue
            stats["attempted"] += 1
            try:
                result = annotator.analyze(content)
                analysis = (
                    result if isinstance(result, Analysis) else Analysis.model_validate(result)
                )
                expected_version = (
                    f"{analysis.annotator}:{analysis.prompt_version}:{analysis.schema_version}"
                )
                if expected_version != annotator.version:
                    raise ValueError("annotator_version_mismatch")
                analysis.verify_against(content)
                with store.transaction():
                    store.save_analysis(dataset_id, content, analysis)
                stats["succeeded"] += 1
            except (ValueError, ValidationError, RuntimeError):
                # Raw exceptions may include sensitive request text; store fixed codes only.
                with store.transaction():
                    store.save_failure(dataset_id, content, annotator.version, "annotation_failed")
                stats["failed"] += 1
                if len(stats["errors"]) < 100:
                    stats["errors"].append(
                        {"content_key": content.key, "code": "annotation_failed"}
                    )
        return {"stats": stats}

    graph = StateGraph(PipelineState)
    graph.add_node("annotate", annotate)
    graph.add_edge(START, "annotate")
    graph.add_edge("annotate", END)
    result = graph.compile().invoke({"dataset_id": dataset_id, "stats": {}})
    return result["stats"]
