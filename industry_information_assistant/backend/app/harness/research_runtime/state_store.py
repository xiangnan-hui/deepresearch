"""统一管理 Research Runtime 的 Redis 状态。"""

import asyncio
from typing import Any, Dict, Optional

try:
    from core.redis_client import cache
except ImportError:
    from app.core.redis_client import cache

from .models import InteractiveResearchState, utc_now


class ResearchStateStore:
    def __init__(self, ttl_seconds: int = 7 * 24 * 3600):
        self.ttl_seconds = ttl_seconds

    @staticmethod
    def _key(research_id: str) -> str:
        return f"research:{research_id}:state"

    async def create(self, state: InteractiveResearchState) -> Dict[str, Any]:
        data = state.to_dict()
        ok = await asyncio.to_thread(cache.set, self._key(state.research_id), data, self.ttl_seconds)
        if not ok:
            raise RuntimeError("无法连接 Redis，研究任务状态创建失败")
        return data

    async def get(self, research_id: str) -> Optional[Dict[str, Any]]:
        return await asyncio.to_thread(cache.get, self._key(research_id))

    async def update(self, research_id: str, **changes: Any) -> Dict[str, Any]:
        state = await self.get(research_id)
        if not state:
            raise KeyError(research_id)
        state.update(changes)
        state["updated_at"] = utc_now()
        ok = await asyncio.to_thread(cache.set, self._key(research_id), state, self.ttl_seconds)
        if not ok:
            raise RuntimeError("研究任务状态更新失败")
        return state

    async def update_progress(self, research_id: str, stage: str, step: str, progress: int) -> Dict[str, Any]:
        return await self.update(
            research_id,
            current_stage=stage,
            current_step=step,
            progress=max(0, min(100, progress)),
        )

    async def update_digest(self, research_id: str, digest: Dict[str, Any]) -> Dict[str, Any]:
        return await self.update(research_id, research_digest=digest)

    async def set_status(self, research_id: str, status: str, **changes: Any) -> Dict[str, Any]:
        return await self.update(research_id, status=status, **changes)
