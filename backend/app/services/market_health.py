from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from threading import Lock
from typing import Any

from app.services.fund_metadata import SOURCE_LABELS


class MarketSourceHealth:
    def __init__(self) -> None:
        self._lock = Lock()
        self._sources: dict[str, dict[str, Any]] = {}
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._sources = {
                source: self._empty_source(source)
                for source in SOURCE_LABELS
            }

    def record(
        self,
        source: str,
        outcome: str,
        error: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if outcome not in {"success", "no_data", "failure"}:
            raise ValueError(f"unsupported source health outcome: {outcome}")
        observed = now or datetime.now()
        with self._lock:
            item = self._sources.setdefault(source, self._empty_source(source))
            item["attempts"] += 1
            counter_key = {
                "success": "successes",
                "no_data": "no_datas",
                "failure": "failures",
            }[outcome]
            item[counter_key] += 1
            item["last_attempt"] = observed.isoformat(timespec="seconds")
            item["last_outcome"] = outcome
            if outcome == "success":
                item["last_success"] = item["last_attempt"]
                item["last_error"] = None
            elif error:
                item["last_error"] = error

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            sources = []
            for item in self._sources.values():
                row = deepcopy(item)
                attempts = row["attempts"]
                row["success_rate"] = round(row["successes"] / attempts * 100, 1) if attempts else None
                row["availability_rate"] = (
                    round((row["successes"] + row["no_datas"]) / attempts * 100, 1)
                    if attempts
                    else None
                )
                row["status"] = _status_for(row)
                sources.append(row)
            return {
                "generated_at": datetime.now().isoformat(timespec="seconds"),
                "sources": sources,
            }

    @staticmethod
    def _empty_source(source: str) -> dict[str, Any]:
        return {
            "source": source,
            "source_label": SOURCE_LABELS.get(source, source),
            "attempts": 0,
            "successes": 0,
            "no_datas": 0,
            "failures": 0,
            "last_attempt": None,
            "last_success": None,
            "last_error": None,
            "last_outcome": None,
        }


def _status_for(item: dict[str, Any]) -> str:
    if not item["attempts"]:
        return "idle"
    if item["last_outcome"] == "failure":
        return "degraded" if item["successes"] else "unavailable"
    if item["last_outcome"] == "no_data":
        return "healthy" if item["successes"] else "no_data"
    return "healthy"


market_source_health = MarketSourceHealth()


def get_source_health() -> dict[str, Any]:
    return market_source_health.snapshot()
