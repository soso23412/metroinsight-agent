from __future__ import annotations

from typing import Literal

from pydantic import Field

from metro_agent.domain.schemas import Contract


class Limits(Contract):
    max_steps: int = Field(default=12, ge=1, le=30)
    max_seconds: float = Field(default=180, gt=0, le=600)
    max_tokens: int = Field(default=100_000, ge=1, le=500_000)
    max_cost_usd: float = Field(default=0.1, ge=0, le=10)


class Task(Contract):
    dataset_id: str = Field(min_length=1, max_length=100)
    annotator_version: str = Field(min_length=1, max_length=200)
    question: str = Field(min_length=1, max_length=2000)
    mode: Literal["offline", "live"] = "offline"
    limits: Limits = Field(default_factory=Limits)


class Filters(Contract):
    city: str | None = Field(default=None, max_length=100)
    line: str | None = Field(default=None, max_length=100)
    start: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")
    end: str | None = Field(default=None, pattern=r"^\d{4}-\d{2}-\d{2}$")


class Empty(Contract):
    pass


class AggregateArgs(Filters):
    group_by: Literal["city", "line", "day", "sentiment", "aspect"] = "sentiment"


class SearchArgs(Filters):
    query: str = Field(default="", max_length=160)
    k: int = Field(default=5, ge=1, le=10)


class ReadArgs(Contract):
    evidence_ids: list[str] = Field(min_length=1, max_length=10)


class FinishArgs(Contract):
    status: Literal["completed", "insufficient_evidence"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=10)
    metric_result_ids: list[str] = Field(default_factory=list, max_length=8)
    timeline_result_ids: list[str] = Field(default_factory=list, max_length=4)
    recommendations: list[str] = Field(default_factory=list, max_length=5)


class Call(Contract):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    arguments: dict


class Decision(Contract):
    calls: list[Call] = Field(min_length=1, max_length=4)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


TOOL_ARGS = {
    "describe_dataset": Empty,
    "aggregate_feedback": AggregateArgs,
    "retrieve_evidence": SearchArgs,
    "read_evidence": ReadArgs,
    "get_event_timeline": Filters,
    "finish_report": FinishArgs,
}

DESCRIPTIONS = {
    "describe_dataset": "Describe the bound dataset, available cities, lines and label coverage.",
    "aggregate_feedback": "Exact SQL counts over the bound scope; groups may overlap for aspects.",
    "retrieve_evidence": "Retrieve source quotes using lexical Chinese FTS5; filters are exact.",
    "read_evidence": "Read only evidence IDs already retrieved in this run.",
    "get_event_timeline": "Publication-time ordering of unverified event candidates, not event time.",
    "finish_report": "Finish with observed evidence IDs and aggregate result IDs, never invented numbers. Completed needs both evidence and metrics. Recommendations are unverified proposals.",
}


def tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": schema.model_json_schema(),
            },
        }
        for name, schema in TOOL_ARGS.items()
    ]
