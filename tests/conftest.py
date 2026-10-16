from pathlib import Path
from uuid import uuid4

import pytest

from metro_agent.domain.schemas import Content, SourceRef


def pytest_configure(config):
    """Keep temporary files inside the checkout on restricted Windows hosts."""
    if config.option.basetemp:
        Path(config.option.basetemp).resolve().parent.mkdir(parents=True, exist_ok=True)
    else:
        parent = Path(config.rootpath) / ".cache" / "test-runs"
        parent.mkdir(parents=True, exist_ok=True)
        config.option.basetemp = str(parent / f"run-{uuid4().hex[:12]}")


@pytest.fixture
def make_content():
    def factory(**changes):
        values = {
            "platform": "synthetic",
            "content_id": "test-1",
            "text": "今天地铁拥挤。",
            "synthetic": True,
            "source": SourceRef(source_sha256="a" * 64, source_name="test.json", row=1),
        }
        return Content(**(values | changes))

    return factory


@pytest.fixture
def write_jsonl(tmp_path: Path):
    import json

    def write(rows, name="contents.jsonl"):
        path = tmp_path / name
        path.write_text(
            "\n".join(
                json.dumps(row, ensure_ascii=False) if not isinstance(row, str) else row
                for row in rows
            ),
            encoding="utf-8",
        )
        return path

    return write
