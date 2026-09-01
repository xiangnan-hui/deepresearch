"""Stable event envelope between agents, LangGraph and SSE."""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


@dataclass
class HarnessEvent:
    type: str
    run_id: str
    session_id: str
    sequence: int
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    node: Optional[str] = None
    phase: Optional[str] = None
    content: Any = None
    data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def wrap(
        cls,
        event: Dict[str, Any],
        *,
        run_id: str,
        session_id: str,
        sequence: int,
    ) -> Dict[str, Any]:
        """Add harness metadata without breaking the existing event schema."""
        wrapped = dict(event)
        wrapped.setdefault("run_id", run_id)
        wrapped.setdefault("session_id", session_id)
        wrapped.setdefault("sequence", sequence)
        wrapped.setdefault("timestamp", datetime.now(timezone.utc).isoformat())
        return wrapped

    def to_dict(self) -> Dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value is not None}
