"""In-process request counters for the /metrics endpoint.

Thread-safe via a single Lock. Values reset on process restart —
documented in tradeoffs.md as acceptable for a portfolio service.
"""

import threading

_lock = threading.Lock()

_counters: dict[str, float | int] = {
    "requests_total": 0,
    "rule_based_count": 0,
    "rule_based_plus_llm_count": 0,
    "llm_judge_fallback_count": 0,  # LLM judge requested but failed
    "latency_ms_total": 0.0,
}


def increment(key: str, value: float = 1.0) -> None:
    with _lock:
        _counters[key] = _counters.get(key, 0) + value


def snapshot() -> dict:
    with _lock:
        data = dict(_counters)
    total = data["requests_total"]
    data["avg_latency_ms"] = round(data["latency_ms_total"] / total, 1) if total > 0 else 0.0
    return data
