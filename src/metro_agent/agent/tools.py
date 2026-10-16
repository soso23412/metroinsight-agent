from __future__ import annotations

import json
from datetime import date

from metro_agent.agent.contracts import TOOL_ARGS, AggregateArgs, Filters, SearchArgs
from metro_agent.domain.schemas import Content
from metro_agent.retrieval.index import INDEX_VERSION, EvidenceIndex
from metro_agent.storage.db import Store


class ToolBox:
    def __init__(self, store: Store, dataset_id: str, version: str):
        if store.dataset_manifest(dataset_id) is None:
            raise ValueError("unknown_dataset")
        self.store, self.dataset_id, self.version = store, dataset_id, version
        self.index = EvidenceIndex(store, dataset_id)

    def _where(self, filters: Filters) -> tuple[str, list]:
        params = [self.dataset_id, self.version]
        clauses = ["c.dataset_id=?", "a.annotator_version=?", "a.status='success'"]
        for field in ("city", "line"):
            value = getattr(filters, field)
            if value is not None:
                clauses.append(f"json_extract(c.payload,'$.{field}')=?")
                params.append(value)
        for field, op in (("start", ">="), ("end", "<=")):
            value = getattr(filters, field)
            if value is not None:
                date.fromisoformat(value)
                # Source timezone dates, deliberately not UTC dates.
                clauses.append(f"substr(json_extract(c.payload,'$.published_at'),1,10){op}?")
                params.append(value)
        if filters.start and filters.end and filters.start > filters.end:
            raise ValueError("invalid_date_range")
        return " AND ".join(clauses), params

    @property
    def join(self) -> str:
        return "contents c JOIN annotations a USING(dataset_id,platform,content_id)"

    def describe(self) -> dict:
        rows = self.store.conn.execute(
            "SELECT json_extract(payload,'$.city'),json_extract(payload,'$.line'),"
            "json_extract(payload,'$.published_at') FROM contents WHERE dataset_id=?",
            (self.dataset_id,),
        ).fetchall()
        coverage = self.store.conn.execute(
            "SELECT status,count(*) FROM annotations WHERE dataset_id=? "
            "AND annotator_version=? GROUP BY status",
            (self.dataset_id, self.version),
        ).fetchall()
        return {
            "dataset_id": self.dataset_id,
            "annotator_version": self.version,
            "synthetic": bool(self.store.dataset_manifest(self.dataset_id).get("synthetic")),
            "total_contents": len(rows),
            "annotation_coverage": dict(coverage),
            "cities": sorted({r[0] for r in rows if r[0]}),
            "lines": sorted({r[1] for r in rows if r[1]}),
            "missing_publication_times": sum(r[2] is None for r in rows),
            "index_version": INDEX_VERSION,
            "grain": "posts; comments excluded; labels are version-specific",
        }

    def aggregate(self, args: AggregateArgs) -> dict:
        where, params = self._where(args)
        base = f"FROM {self.join} WHERE {where}"
        total = self.store.conn.execute(f"SELECT count(*) {base}", params).fetchone()[0]
        relevant = " AND json_extract(a.payload,'$.relevance')='relevant'"
        denominator = self.store.conn.execute(
            f"SELECT count(*) {base}{relevant}",
            params,
        ).fetchone()[0]
        group = {
            "city": "json_extract(c.payload,'$.city')",
            "line": "json_extract(c.payload,'$.line')",
            "day": "substr(json_extract(c.payload,'$.published_at'),1,10)",
            "sentiment": "json_extract(a.payload,'$.sentiment')",
            "aspect": "j.value",
        }[args.group_by]
        join = self.join
        if args.group_by == "aspect":
            join += ",json_each(a.payload,'$.aspects') j"
        groups = self.store.conn.execute(
            f"SELECT coalesce({group},'unknown'),count(*) FROM {join} "
            f"WHERE {where}{relevant} GROUP BY 1 ORDER BY 2 DESC,1 LIMIT 101",
            params,
        ).fetchall()
        return {
            "filters": args.model_dump(),
            "annotated_total": total,
            "relevant_denominator": denominator,
            "group_by": args.group_by,
            "groups": [{"label": r[0], "count": r[1]} for r in groups[:100]],
            "truncated": len(groups) > 100,
            "scope": "all matching successfully annotated posts; not population satisfaction",
            "overlapping": args.group_by == "aspect",
        }

    def retrieve(self, args: SearchArgs) -> dict:
        where, params = self._where(args)
        rows = self.store.conn.execute(
            f"SELECT c.payload FROM {self.join} WHERE {where} ORDER BY c.platform,c.content_id",
            params,
        )
        # Filters precede top-k. Exhaust candidates to avoid a global-top-k filter leak/miss.
        candidates = {c.key: c for row in rows if (c := Content.model_validate_json(row[0]))}
        if args.query.strip():
            keys = self.index.search(args.query, max(1, self.store.count_contents(self.dataset_id)))
        else:
            keys = list(candidates)
        found = [candidates[key] for key in keys if key in candidates][: args.k]
        return {
            "query": args.query,
            "index_version": INDEX_VERSION,
            "evidence": [
                {
                    "evidence_id": c.key,
                    "platform": c.platform,
                    "content_id": c.content_id,
                    "quote": c.text[:1200],
                    "quote_start": 0,
                    "quote_end": min(1200, len(c.text)),
                    "text_sha256": c.text_sha256,
                    "city": c.city,
                    "line": c.line,
                    "published_at": c.published_at.isoformat() if c.published_at else None,
                    "source": c.source.model_dump(),
                    "synthetic": c.synthetic,
                }
                for c in found
            ],
            "empty": not found,
            "note": "Top-k are evidence examples, never a statistical sample.",
        }

    def timeline(self, args: Filters) -> dict:
        where, params = self._where(args)
        rows = self.store.conn.execute(
            f"SELECT c.payload,a.payload FROM {self.join} WHERE {where} "
            "AND json_extract(a.payload,'$.event_candidate')=1 "
            "ORDER BY json_extract(c.payload,'$.published_at'),c.content_id LIMIT 51",
            params,
        ).fetchall()
        return {
            "items": [
                {
                    "content_id": json.loads(r[0])["content_id"],
                    "published_at": json.loads(r[0]).get("published_at"),
                    "event_type": json.loads(r[1]).get("event_type"),
                    "verification": "unverified",
                }
                for r in rows[:50]
            ],
            "truncated": len(rows) > 50,
            "time_basis": "post publication, NOT described event time; candidates unverified",
        }

    def execute(self, name: str, arguments: dict, visible: dict) -> dict:
        if name not in TOOL_ARGS or name == "finish_report":
            raise ValueError("unknown_tool")
        args = TOOL_ARGS[name].model_validate(arguments)
        if name == "describe_dataset":
            return self.describe()
        if name == "aggregate_feedback":
            return self.aggregate(args)
        if name == "retrieve_evidence":
            return self.retrieve(args)
        if name == "get_event_timeline":
            return self.timeline(args)
        if any(key not in visible for key in args.evidence_ids):
            raise ValueError("evidence_not_visible")
        return {"evidence": [visible[key] for key in args.evidence_ids]}

    def close(self) -> None:
        self.index.close()
