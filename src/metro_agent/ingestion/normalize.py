from __future__ import annotations

import math
import re
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

CHINA = timezone(timedelta(hours=8), "Asia/Shanghai")


def file_sha256(path: Path) -> str:
    import hashlib

    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identifier(value: object) -> str:
    # JSON numeric identifiers may already have lost precision. Never coerce them.
    if not isinstance(value, str) or not value.strip():
        raise ValueError("identifier_must_be_nonempty_string")
    return value.strip()


def count(value: object) -> tuple[int | None, str | None]:
    if value is None or value == "":
        return None, None
    if isinstance(value, bool):
        return None, "invalid_count"
    text = str(value).strip().lower().replace(",", "")
    match = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([万亿wk]?)", text)
    if not match:
        return None, "invalid_count"
    number = (
        float(match[1]) * {"": 1, "万": 10_000, "亿": 100_000_000, "w": 10_000, "k": 1000}[match[2]]
    )
    if not math.isfinite(number) or number > 2**63 - 1:
        return None, "invalid_count"
    return int(number), None


def timestamp(value: object) -> tuple[datetime | None, str | None]:
    if value is None or value == "" or value == 0:
        return None, None
    try:
        if isinstance(value, bool):
            raise ValueError
        if isinstance(value, (int, float)) or re.fullmatch(r"\d+(?:\.\d+)?", str(value)):
            number = float(value)
            seconds = number / 1000 if number >= 100_000_000_000 else number
            return datetime.fromtimestamp(seconds, UTC).astimezone(CHINA), None
        text = str(value).strip()
        if "年" in text:
            parsed = datetime.strptime(text, "%Y年%m月%d日%H:%M")
        else:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        # Legacy unzoned exports use a documented Shanghai local-time convention.
        return parsed.replace(tzinfo=CHINA) if parsed.tzinfo is None else parsed.astimezone(
            CHINA
        ), None
    except (TypeError, ValueError, OverflowError, OSError):
        return None, "invalid_timestamp"


def public_url(value: object) -> str | None:
    if not value:
        return None
    try:
        url = urlsplit(str(value))
        if url.scheme not in {"http", "https"} or not url.hostname or url.username or url.password:
            return None
        # Strip all query/fragment values, including platform authentication tokens.
        return urlunsplit((url.scheme, url.netloc, url.path, "", ""))
    except ValueError:
        return None
