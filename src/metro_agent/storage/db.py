from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

from metro_agent.domain.schemas import Analysis, Comment, Content

SCHEMA_VERSION = 1


class Store:
    """Never open an unrelated / historical database as this application's output."""

    def __init__(self, path: Path | str):
        self.path = path
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        names = {
            r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        if names and "metro_schema" not in names:
            self.conn.close()
            raise ValueError("refusing_unrecognized_database: choose a NEW output database")
        self.conn.execute("PRAGMA foreign_keys=ON")
        if not names:
            self._initialize()
        version = self.conn.execute("SELECT version FROM metro_schema").fetchone()
        if version is None or version[0] != SCHEMA_VERSION:
            self.conn.close()
            raise ValueError("unsupported_database_schema")

    def _initialize(self) -> None:
        self.conn.executescript("""
            CREATE TABLE metro_schema(version INTEGER NOT NULL);
            INSERT INTO metro_schema VALUES (1);
            CREATE TABLE datasets(
                dataset_id TEXT PRIMARY KEY,
                manifest TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE contents(
                dataset_id TEXT NOT NULL REFERENCES datasets(dataset_id),
                platform TEXT NOT NULL,
                content_id TEXT NOT NULL,
                text_sha256 TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY(dataset_id, platform, content_id)
            );
            CREATE TABLE comments(
                dataset_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                comment_id TEXT NOT NULL,
                content_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                PRIMARY KEY(dataset_id, platform, comment_id),
                FOREIGN KEY(dataset_id,platform,content_id)
                    REFERENCES contents(dataset_id,platform,content_id)
            );
            CREATE TABLE annotations(
                dataset_id TEXT NOT NULL,
                platform TEXT NOT NULL,
                content_id TEXT NOT NULL,
                annotator_version TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('success','failed')),
                payload TEXT,
                error_code TEXT,
                PRIMARY KEY(dataset_id,platform,content_id,annotator_version),
                FOREIGN KEY(dataset_id,platform,content_id)
                    REFERENCES contents(dataset_id,platform,content_id)
            );
        """)
        self.conn.commit()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self.conn:
            yield

    def add_dataset(self, dataset_id: str, manifest: dict) -> None:
        self.conn.execute(
            "INSERT INTO datasets VALUES (?, ?, ?)",
            (dataset_id, json.dumps(manifest, ensure_ascii=False), datetime.now(UTC).isoformat()),
        )

    def dataset_manifest(self, dataset_id: str) -> dict | None:
        row = self.conn.execute(
            "SELECT manifest FROM datasets WHERE dataset_id=?", (dataset_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def update_manifest(self, dataset_id: str, manifest: dict) -> None:
        self.conn.execute(
            "UPDATE datasets SET manifest=? WHERE dataset_id=?",
            (json.dumps(manifest, ensure_ascii=False), dataset_id),
        )

    def add_content(self, dataset_id: str, content: Content) -> str:
        existing = self.conn.execute(
            "SELECT payload FROM contents WHERE dataset_id=? AND platform=? AND content_id=?",
            (dataset_id, content.platform, content.content_id),
        ).fetchone()
        if existing:
            prior = Content.model_validate_json(existing[0])
            return "duplicate" if prior.text_sha256 == content.text_sha256 else "id_conflict"
        self.conn.execute(
            "INSERT INTO contents VALUES (?, ?, ?, ?, ?)",
            (
                dataset_id,
                content.platform,
                content.content_id,
                content.text_sha256,
                content.model_dump_json(),
            ),
        )
        return "inserted"

    def add_comment(self, dataset_id: str, comment: Comment) -> str:
        parent = self.conn.execute(
            "SELECT 1 FROM contents WHERE dataset_id=? AND platform=? AND content_id=?",
            (dataset_id, comment.platform, comment.content_id),
        ).fetchone()
        if not parent:
            return "orphan_comment"
        existing = self.conn.execute(
            "SELECT payload FROM comments WHERE dataset_id=? AND platform=? AND comment_id=?",
            (dataset_id, comment.platform, comment.comment_id),
        ).fetchone()
        if existing:
            prior = Comment.model_validate_json(existing[0])
            return (
                "duplicate"
                if prior.text == comment.text and prior.content_id == comment.content_id
                else "id_conflict"
            )
        self.conn.execute(
            "INSERT INTO comments VALUES (?, ?, ?, ?, ?)",
            (
                dataset_id,
                comment.platform,
                comment.comment_id,
                comment.content_id,
                comment.model_dump_json(),
            ),
        )
        return "inserted"

    def iter_contents(self, dataset_id: str) -> Iterator[Content]:
        for row in self.conn.execute(
            "SELECT payload FROM contents WHERE dataset_id=? ORDER BY platform,content_id",
            (dataset_id,),
        ):
            yield Content.model_validate_json(row[0])

    def get_content(self, dataset_id: str, platform: str, content_id: str) -> Content | None:
        row = self.conn.execute(
            "SELECT payload FROM contents WHERE dataset_id=? AND platform=? AND content_id=?",
            (dataset_id, platform, content_id),
        ).fetchone()
        return Content.model_validate_json(row[0]) if row else None

    def save_analysis(self, dataset_id: str, content: Content, analysis: Analysis) -> None:
        analysis.verify_against(content)
        version = f"{analysis.annotator}:{analysis.prompt_version}:{analysis.schema_version}"
        self.conn.execute(
            "INSERT INTO annotations VALUES (?, ?, ?, ?, 'success', ?, NULL) "
            "ON CONFLICT(dataset_id,platform,content_id,annotator_version) DO UPDATE SET "
            "status='success',payload=excluded.payload,error_code=NULL",
            (dataset_id, content.platform, content.content_id, version, analysis.model_dump_json()),
        )

    def save_failure(self, dataset_id: str, content: Content, version: str, code: str) -> None:
        self.conn.execute(
            "INSERT INTO annotations VALUES (?, ?, ?, ?, 'failed', NULL, ?) "
            "ON CONFLICT(dataset_id,platform,content_id,annotator_version) DO UPDATE SET "
            "status='failed',payload=NULL,error_code=excluded.error_code",
            (dataset_id, content.platform, content.content_id, version, code),
        )

    def annotation(self, dataset_id: str, content: Content, version: str) -> Analysis | None:
        row = self.conn.execute(
            "SELECT payload FROM annotations WHERE dataset_id=? AND platform=? AND content_id=? "
            "AND annotator_version=? AND status='success'",
            (dataset_id, content.platform, content.content_id, version),
        ).fetchone()
        return Analysis.model_validate_json(row[0]) if row else None

    def count_contents(self, dataset_id: str) -> int:
        return self.conn.execute(
            "SELECT count(*) FROM contents WHERE dataset_id=?", (dataset_id,)
        ).fetchone()[0]

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()
