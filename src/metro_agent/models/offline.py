"""Deterministic policy for synthetic contract demos, NOT an LLM."""

from __future__ import annotations

import json
import re

from metro_agent.agent.contracts import Call, Decision


class OfflineChat:
    identity = "offline-policy-v1"
    live = False

    def reserve(self, messages: list[dict]) -> tuple[int, float]:
        return 0, 0.0

    def decide(self, messages: list[dict], timeout: float) -> Decision:
        question = messages[1]["content"]
        receipts = [json.loads(m["content"]) for m in messages if m["role"] == "tool"]
        observed = {r["tool"]: r for r in receipts if r.get("ok")}
        filters = {}
        if "describe_dataset" in observed:
            description = observed["describe_dataset"]["data"]
            for field, options in (("city", description["cities"]), ("line", description["lines"])):
                match = next((s for s in options if s in question), None)
                if match:
                    filters[field] = match
            line = re.search(r"(?:示例)?\d+号线", question)
            if line:
                filters["line"] = line.group()
        if not observed:
            name, args = "describe_dataset", {}
        elif "aggregate_feedback" not in observed:
            group = "aspect" if any(s in question for s in ("维度", "问题类型")) else "sentiment"
            name, args = "aggregate_feedback", {**filters, "group_by": group}
        elif "retrieve_evidence" not in observed:
            keywords = [
                s for s in ("拥挤", "晚点", "故障", "无障碍", "垃圾", "支付") if s in question
            ]
            name, args = "retrieve_evidence", {**filters, "query": " ".join(keywords), "k": 5}
        elif (
            any(s in question for s in ("事件", "时间线")) and "get_event_timeline" not in observed
        ):
            name, args = "get_event_timeline", filters
        else:
            evidence = observed["retrieve_evidence"]["data"]["evidence"]
            name, args = (
                "finish_report",
                {
                    "status": "completed" if evidence else "insufficient_evidence",
                    "evidence_ids": [e["evidence_id"] for e in evidence],
                    "metric_result_ids": [observed["aggregate_feedback"]["result_id"]],
                    "timeline_result_ids": (
                        [observed["get_event_timeline"]["result_id"]]
                        if "get_event_timeline" in observed
                        else []
                    ),
                },
            )
        return Decision(calls=[Call(id=f"offline-{len(receipts)}", name=name, arguments=args)])
