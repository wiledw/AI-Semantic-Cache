from __future__ import annotations

import math
from typing import Iterable, Sequence


def cosine_similarity(vec_a: Sequence[float], vec_b: Sequence[float]) -> float:
    if len(vec_a) != len(vec_b):
        return 0.0
    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for a, b in zip(vec_a, vec_b):
        dot += a * b
        norm_a += a * a
        norm_b += b * b
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (math.sqrt(norm_a) * math.sqrt(norm_b))


def normalize_query(text: str) -> str:
    return " ".join(text.lower().strip().split())


def as_float_list(values: Iterable[float]) -> list[float]:
    return [float(v) for v in values]
