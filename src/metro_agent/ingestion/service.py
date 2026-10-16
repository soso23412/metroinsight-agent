from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from metro_agent.domain.schemas import ImportResult
from metro_agent.ingestion import adapters
from metro_agent.ingestion.normalize import file_sha256
from metro_agent.storage.db import Store


def _account(result: ImportResult, status: str, source_name: str, row: int) -> None:
    if status == "inserted":
        result.accepted += 1
    elif status == "duplicate":
        result.duplicates += 1
    else:
        result.rejected += 1
        result.issue(source_name, row, status)


def ingest(store: Store, path: Path, *, kind: str, comments_path: Path | None = None) -> dict:
    if kind not in {"xhs", "weibo"}:
        raise ValueError("unsupported_adapter")
    if comments_path and kind != "xhs":
        raise ValueError("comments_supported_only_for_xhs")
    paths = [path] + ([comments_path] if comments_path else [])
    initial = {p: (p.stat().st_size, p.stat().st_mtime_ns) for p in paths}
    files = [{"name": p.name, "sha256": file_sha256(p)} for p in paths]
    fingerprint = "schema-1:import-1\0" + kind + "\0" + "\0".join(f["sha256"] for f in files)
    dataset_id = sha256(fingerprint.encode()).hexdigest()[:24]
    previous = store.dataset_manifest(dataset_id)
    if previous is not None:
        return {**previous, "reused": True}
    content_stats, comment_stats = ImportResult(), ImportResult()
    manifest = {
        "dataset_id": dataset_id,
        "schema_version": "1",
        "adapter_version": "1",
        "adapter": kind,
        "sources": files,
    }
    with store.transaction():
        store.add_dataset(dataset_id, manifest)
        for content in adapters.contents(path, kind, content_stats):
            _account(
                content_stats,
                store.add_content(dataset_id, content),
                path.name,
                content.source.row,
            )
        if comments_path:
            for comment in adapters.comments(comments_path, comment_stats):
                _account(
                    comment_stats,
                    store.add_comment(dataset_id, comment),
                    comments_path.name,
                    comment.source.row,
                )
        for p in paths:
            if (p.stat().st_size, p.stat().st_mtime_ns) != initial[p]:
                raise ValueError("input_file_changed_during_import")
        content_stats.verify_counts()
        comment_stats.verify_counts()
        manifest.update(
            contents=content_stats.model_dump(),
            comments=comment_stats.model_dump(),
            reused=False,
        )
        store.update_manifest(dataset_id, manifest)
    return manifest
