"""Deterministic quality gates applied after graph execution."""

from datetime import datetime, timedelta
from typing import Any, Dict, Iterable, Optional


class FreshnessEvaluator:
    def evaluate(self, state: Dict[str, Any]) -> Dict[str, Any]:
        context = state.get("run_context", {})
        policy = context.get("freshness", {})
        if not policy.get("required"):
            return {"required": False, "passed": True, "recent_sources": 0}

        window_days = int(policy.get("window_days") or 365)
        minimum = int(policy.get("minimum_recent_sources") or 0)
        current_time = self._parse_datetime(context.get("current_time")) or datetime.now()
        cutoff = current_time.replace(tzinfo=None) - timedelta(days=window_days)
        recent_urls = set()

        for item in self._evidence(state):
            published = self._published_at(item)
            if published and published.replace(tzinfo=None) >= cutoff:
                recent_urls.add(item.get("source_url") or item.get("url") or str(id(item)))

        count = len(recent_urls)
        return {
            "required": True,
            "passed": count >= minimum,
            "recent_sources": count,
            "minimum_recent_sources": minimum,
            "cutoff": cutoff.date().isoformat(),
        }

    @staticmethod
    def _evidence(state: Dict[str, Any]) -> Iterable[Dict[str, Any]]:
        yield from (item for item in state.get("facts", []) if isinstance(item, dict))
        yield from (item for item in state.get("raw_sources", []) if isinstance(item, dict))

    @classmethod
    def _published_at(cls, item: Dict[str, Any]) -> Optional[datetime]:
        metadata = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        for key in ("published_at", "published_date", "date", "publish_time"):
            parsed = cls._parse_datetime(item.get(key) or metadata.get(key))
            if parsed:
                return parsed
        return None

    @staticmethod
    def _parse_datetime(value: Any) -> Optional[datetime]:
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        text = str(value).strip().replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            try:
                return datetime.strptime(text[:10], "%Y-%m-%d")
            except ValueError:
                return None
