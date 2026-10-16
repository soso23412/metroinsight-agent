"""Small auditable train-only TF-IDF nearest-centroid and majority baselines."""

from __future__ import annotations

import math
from collections import Counter, defaultdict

from metro_agent.retrieval.index import tokens


def baseline_predict(train: list[dict], test: list[dict], field: str) -> dict:
    if not train or not test:
        raise ValueError("train_and_test_required")
    group_train = {r["group_id"] for r in train}
    if any(r["group_id"] in group_train for r in test):
        raise ValueError("split_leakage")
    documents = [Counter(tokens(r["text"])) for r in train]
    df = Counter(token for doc in documents for token in doc)
    idf = {term: math.log((1 + len(train)) / (1 + count)) + 1 for term, count in df.items()}

    def vector(text):
        counts = Counter(tokens(text))
        values = {t: (1 + math.log(n)) * idf[t] for t, n in counts.items() if t in idf}
        norm = math.sqrt(sum(v * v for v in values.values())) or 1
        return {t: v / norm for t, v in values.items()}

    centroids = defaultdict(Counter)
    labels = Counter(r["analysis"][field] for r in train)
    for record in train:
        centroids[record["analysis"][field]].update(vector(record["text"]))
    for label, values in centroids.items():
        norm = math.sqrt(sum(v * v for v in values.values())) or 1
        centroids[label] = {t: v / norm for t, v in values.items()}
    majority = sorted(labels, key=lambda label: (-labels[label], label))[0]
    predictions = []
    for record in test:
        v = vector(record["text"])
        scores = {
            label: sum(value * centroid.get(term, 0) for term, value in v.items())
            for label, centroid in centroids.items()
        }
        predictions.append(
            sorted(scores, key=lambda label: (-scores[label], label))[0] if v else majority
        )
    return {
        "majority": [majority] * len(test),
        "tfidf_centroid": predictions,
        "vocabulary_size_train_only": len(idf),
        "version": "stdlib-tfidf-centroid-v1",
    }
