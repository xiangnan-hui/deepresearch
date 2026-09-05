"""基于 Redis Stream 的可回放研究事件总线。"""

import asyncio
import json
from typing import Any, Dict, List, Tuple
from redis.exceptions import ConnectionError as RedisConnectionError, TimeoutError as RedisTimeoutError

try:
    from core.redis_client import get_redis_client
except ImportError:
    from app.core.redis_client import get_redis_client

from .models import utc_now


class ResearchEventBus:
    def __init__(self, max_length: int = 5000):
        self.client = get_redis_client()
        self.max_length = max_length

    @staticmethod
    def _key(research_id: str) -> str:
        return f"research:{research_id}:events"

    async def publish(self, research_id: str, event_type: str, payload: Dict[str, Any]) -> str:
        event = {
            "research_id": research_id,
            "type": event_type,
            "timestamp": utc_now(),
            "payload": payload,
        }
        event_id = await asyncio.to_thread(
            self.client.xadd,
            self._key(research_id),
            {"event": json.dumps(event, ensure_ascii=False, default=str)},
            maxlen=self.max_length,
            approximate=True,
        )
        return str(event_id)

    async def read(self, research_id: str, after_id: str = "0-0", block_ms: int = 5000) -> List[Tuple[str, Dict[str, Any]]]:
        try:
            rows = await asyncio.to_thread(
                self.client.xread,
                {self._key(research_id): after_id},
                count=100,
                block=block_ms,
            )
        except (RedisTimeoutError, RedisConnectionError):
            # 阻塞读超时属于正常空闲状态，由 SSE 层发送心跳并继续读取。
            return []
        events: List[Tuple[str, Dict[str, Any]]] = []
        for _, messages in rows:
            for event_id, fields in messages:
                event = json.loads(fields["event"])
                event["event_id"] = str(event_id)
                events.append((str(event_id), event))
        return events
