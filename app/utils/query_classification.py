from __future__ import annotations


TIME_SENSITIVE_KEYWORDS = {
    "today",
    "now",
    "current",
    "weather",
    "news",
    "price",
    "score",
}


def is_time_sensitive(query: str) -> bool:
    lowered = query.lower()
    return any(keyword in lowered for keyword in TIME_SENSITIVE_KEYWORDS)
