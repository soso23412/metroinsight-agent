from __future__ import annotations

from collections import Counter


def classification_metrics(truth: list[str], predictions: list[str], labels: list[str]) -> dict:
    if len(truth) != len(predictions) or not truth or not labels:
        raise ValueError("metric_shape_mismatch")
    if any(label not in labels for label in truth):
        raise ValueError("unknown_reference_label")
    confusion = Counter(zip(truth, predictions, strict=True))
    classes = {}
    for label in labels:
        tp = confusion[label, label]
        support = sum(t == label for t in truth)
        predicted = sum(p == label for p in predictions)
        precision, recall = tp / predicted if predicted else 0.0, tp / support if support else 0.0
        classes[label] = {
            "support": support,
            "predicted": predicted,
            "precision": precision,
            "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        }
    return {
        "n": len(truth),
        "accuracy": sum(t == p for t, p in zip(truth, predictions, strict=True)) / len(truth),
        "macro_f1": sum(c["f1"] for c in classes.values()) / len(labels),
        "classes": classes,
        "confusion": [
            {"truth": t, "predicted": p, "count": n} for (t, p), n in sorted(confusion.items())
        ],
        "invalid_predictions": sum(p not in labels for p in predictions),
        "macro_policy": "all declared labels, zero division=0; absent classes have F1=0",
    }


def multilabel_metrics(
    truth: list[set[str]], predictions: list[set[str]], labels: list[str]
) -> dict:
    if not truth or len(truth) != len(predictions):
        raise ValueError("metric_shape_mismatch")
    classes = {}
    total_tp = total_fp = total_fn = 0
    for label in labels:
        tp = sum(label in t and label in p for t, p in zip(truth, predictions, strict=True))
        fp = sum(label not in t and label in p for t, p in zip(truth, predictions, strict=True))
        fn = sum(label in t and label not in p for t, p in zip(truth, predictions, strict=True))
        classes[label] = {
            "support": tp + fn,
            "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        }
        total_tp += tp
        total_fp += fp
        total_fn += fn
    denominator = 2 * total_tp + total_fp + total_fn
    return {
        "n": len(truth),
        "classes": classes,
        "macro_f1": sum(c["f1"] for c in classes.values()) / len(labels),
        "micro_f1": 2 * total_tp / denominator if denominator else 0.0,
    }


def retrieval_recall(expected: set[str], retrieved: list[str], k: int) -> float | None:
    if not expected:
        return None  # Empty-evidence queries are scored separately, not as perfect recall.
    return len(expected & set(retrieved[:k])) / len(expected)
