from __future__ import annotations

import re
import sqlite3

from metro_agent.storage.db import Store

INDEX_VERSION = "zh-bigram-fts5-v1"


def tokens(text: str) -> list[str]:
    result = re.findall(r"[a-z0-9]+", text.lower())
    for part in re.findall(r"[\u3400-\u9fff]+", text):
        result.extend(part[i : i + 2] for i in range(len(part) - 1))
        result.extend(part)  # A one-character station/query still has a recall path.
    return list(dict.fromkeys(result))


class EvidenceIndex:
    """In-memory FTS scoped to one immutable dataset; never mix dataset rows."""

    def __init__(self, store: Store, dataset_id: str):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE VIRTUAL TABLE docs USING fts5(key UNINDEXED, terms)")
        self.conn.executemany(
            "INSERT INTO docs VALUES (?,?)",
            ((c.key, " ".join(tokens(c.text))) for c in store.iter_contents(dataset_id)),
        )

    def search(self, query: str, k: int = 100) -> list[str]:
        terms = tokens(query)
        if not terms:
            return []
        # Only generated alphanumerics / CJK tokens enter MATCH syntax.
        match = " OR ".join('"' + term + '"' for term in terms)
        return [
            r[0]
            for r in self.conn.execute(
                "SELECT key FROM docs WHERE docs MATCH ? ORDER BY bm25(docs),key LIMIT ?",
                (match, k),
            )
        ]

    def close(self) -> None:
        self.conn.close()
