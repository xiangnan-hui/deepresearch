"""Research Runtime 对外数据协议。"""

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ResearchStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FAILED = "failed"


class CommandType(str, Enum):
    ADD_CONSTRAINT = "ADD_CONSTRAINT"
    ADD_QUESTION = "ADD_QUESTION"
    CHANGE_DIRECTION = "CHANGE_DIRECTION"
    PRIORITIZE_GAP = "PRIORITIZE_GAP"
    PAUSE = "PAUSE"
    RESUME = "RESUME"
    CANCEL = "CANCEL"


@dataclass
class ResearchDigest:
    summary: str = "研究任务已创建，等待执行。"
    key_findings: List[str] = field(default_factory=list)
    uncertainties: List[str] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    current_focus: str = ""
    next_steps: List[str] = field(default_factory=list)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class InteractiveResearchState:
    research_id: str
    session_id: str
    query: str
    status: str = ResearchStatus.QUEUED.value
    current_stage: str = "queued"
    current_step: str = ""
    progress: int = 0
    research_plan: List[Dict[str, Any]] = field(default_factory=list)
    plan_version: int = 1
    confirmed_findings: List[Dict[str, Any]] = field(default_factory=list)
    tentative_findings: List[Dict[str, Any]] = field(default_factory=list)
    remaining_gaps: List[str] = field(default_factory=list)
    recent_search_results: List[Dict[str, Any]] = field(default_factory=list)
    user_constraints: List[str] = field(default_factory=list)
    research_digest: Dict[str, Any] = field(default_factory=lambda: ResearchDigest().to_dict())
    checkpoint_id: Optional[str] = None
    performance_summary: Dict[str, Any] = field(default_factory=dict)
    search_count: int = 0
    search_cache_hits: int = 0
    error: Optional[str] = None
    created_at: str = field(default_factory=utc_now)
    updated_at: str = field(default_factory=utc_now)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
