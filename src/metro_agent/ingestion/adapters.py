from __future__ import annotations

import csv
import json
from collections.abc import Iterator
from pathlib import Path

from pydantic import ValidationError

from metro_agent.domain.schemas import Comment, Content, ImportResult, SourceRef
from metro_agent.ingestion.normalize import count, file_sha256, identifier, public_url, timestamp


def _media_count(raw: object) -> int:
    if isinstance(raw, list):
        return sum(bool(public_url(value)) for value in raw)
    if isinstance(raw, str):
        return sum(bool(public_url(value.strip())) for value in raw.split(","))
    return 0


def _content(item: dict, source: SourceRef, kind: str) -> Content:
    warnings = []
    if kind == "xhs":
        original_id = identifier(item.get("note_id"))
        title = str(item.get("title") or "").strip()
        description = str(item.get("desc") or "").strip()
        text = "\n".join(filter(None, [title, description]))
        raw_time, likes, comments = (
            item.get("time"),
            item.get("liked_count"),
            item.get("comment_count"),
        )
        platform, url = "xhs", public_url(item.get("note_url"))
    elif kind == "weibo":
        original_id = identifier(item.get("微博id", item.get("content_id")))
        title = str(item.get("title") or "").strip()
        text = str(item.get("正文", item.get("text")) or "").strip()
        raw_time, likes, comments = item.get("时间"), item.get("点赞数"), item.get("评论数")
        platform, url = "weibo", public_url(item.get("url"))
        if original_id.endswith(".0") or "e+" in original_id.lower():
            warnings.append("possibly_lossy_legacy_id")
    else:
        raise ValueError("unsupported_adapter")
    published, time_warning = timestamp(raw_time)
    like_count, like_warning = count(likes)
    comment_count, comment_warning = count(comments)
    warnings.extend(w for w in [time_warning, like_warning, comment_warning] if w)
    return Content(
        platform=platform,
        content_id=original_id,
        title=title,
        text=text,
        url=url,
        published_at=published,
        source_keyword=str(item.get("source_keyword") or "") or None,
        like_count=like_count,
        comment_count=comment_count,
        source=source,
        warnings=warnings,
    )


def contents(path: Path, kind: str, result: ImportResult) -> Iterator[Content]:
    """Stream records while accounting for every nonblank JSON line / CSV data row."""
    checksum = file_sha256(path)
    with path.open(encoding="utf-8-sig", newline="") as stream:
        if kind == "weibo":
            reader = csv.DictReader(stream)
            fields = reader.fieldnames or []
            if not ({"微博id", "正文"} <= set(fields) or {"content_id", "text"} <= set(fields)):
                raise ValueError("weibo_csv_missing_headers")
            records = enumerate(reader, start=2)
        else:
            records = enumerate(stream, start=1)
        for row, raw in records:
            if isinstance(raw, str) and not raw.strip():
                continue
            result.input_rows += 1
            try:
                item = json.loads(raw) if isinstance(raw, str) else raw
                if not isinstance(item, dict):
                    raise ValueError("record_must_be_object")
                source = SourceRef(source_sha256=checksum, source_name=path.name, row=row)
                content = _content(item, source, kind)
            except (ValueError, TypeError, ValidationError):
                result.rejected += 1
                result.issue(path.name, row, "invalid_record")
                continue
            if content.warnings:
                result.warning_rows += 1
                result.issue(path.name, row, ",".join(content.warnings))
            # The caller accounts acceptance only after successful persistence.
            yield content


def comments(path: Path, result: ImportResult) -> Iterator[Comment]:
    checksum = file_sha256(path)
    with path.open(encoding="utf-8-sig") as stream:
        for row, raw in enumerate(stream, 1):
            if not raw.strip():
                continue
            result.input_rows += 1
            try:
                item = json.loads(raw)
                if not isinstance(item, dict):
                    raise ValueError("record_must_be_object")
                created, warning = timestamp(item.get("create_time"))
                text = str(item.get("content") or "").strip()
                media_count = _media_count(item.get("pictures"))
                text_status = "present" if text else "media_only" if media_count else "empty"
                warnings = [warning] if warning else []
                if not text:
                    warnings.append("comment_" + text_status)
                comment = Comment(
                    platform="xhs",
                    comment_id=identifier(item.get("comment_id")),
                    content_id=identifier(item.get("note_id")),
                    text=text,
                    media_count=media_count,
                    text_status=text_status,
                    created_at=created,
                    parent_comment_id=str(item.get("parent_comment_id") or "") or None,
                    source=SourceRef(source_sha256=checksum, source_name=path.name, row=row),
                    warnings=warnings,
                )
            except (ValueError, TypeError, ValidationError):
                result.rejected += 1
                result.issue(path.name, row, "invalid_comment")
                continue
            if warnings:
                result.warning_rows += 1
                result.issue(path.name, row, ",".join(warnings))
            yield comment
