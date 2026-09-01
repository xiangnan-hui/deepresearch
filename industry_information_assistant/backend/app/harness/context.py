"""Per-run context and policies shared by every graph node."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional
from zoneinfo import ZoneInfo


_FRESHNESS_TERMS = (
    "最新", "最近", "近期", "当前", "目前", "今年", "前沿", "today", "latest",
    "recent", "current", "newest", "state of the art", "sota",
)


@dataclass(frozen=True)
class FreshnessPolicy:
    """Retrieval requirements inferred from the user's question."""

    required: bool = False
    window_days: Optional[int] = None
    search_freshness: str = "noLimit"
    minimum_recent_sources: int = 0

    @classmethod
    def from_query(cls, query: str) -> "FreshnessPolicy":
        normalized = query.casefold()
        if any(term in normalized for term in _FRESHNESS_TERMS):
            return cls(
                required=True,
                window_days=365,
                search_freshness="oneYear",
                minimum_recent_sources=3,
            )
        return cls()


@dataclass(frozen=True)
class RunContext:
    """Immutable execution context injected into LangGraph state."""

    run_id: str
    session_id: str
    current_time: str
    timezone: str
    user_id: Optional[str] = None
    model: Optional[str] = None
    freshness: FreshnessPolicy = field(default_factory=FreshnessPolicy)

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        session_id: str,
        query: str,
        user_id: Optional[str] = None,
        model: Optional[str] = None,
        timezone: str = "Asia/Shanghai",
    ) -> "RunContext":
        now = datetime.now(ZoneInfo(timezone))
        return cls(
            run_id=run_id,
            session_id=session_id,
            current_time=now.isoformat(),
            timezone=timezone,
            user_id=user_id,
            model=model,
            freshness=FreshnessPolicy.from_query(query),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
