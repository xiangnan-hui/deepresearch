"""Fast Agent 到 Slow Worker 的命令队列。"""

import asyncio
import json
import uuid
from typing import Any, Dict, List, Tuple

try:
    from core.redis_client import get_redis_client
except ImportError:
    from app.core.redis_client import get_redis_client

from .models import CommandType, utc_now


class ResearchCommandBus:
    def __init__(self):
        self.client = get_redis_client()

    @staticmethod
    def _key(research_id: str) -> str:
        return f"research:{research_id}:commands"

    async def publish(self, research_id: str, command_type: CommandType, payload: Dict[str, Any]) -> Dict[str, Any]:
        command = {
            "command_id": f"cmd_{uuid.uuid4().hex}",
            "research_id": research_id,
            "type": command_type.value,
            "payload": payload,
            "created_at": utc_now(),
        }
        stream_id = await asyncio.to_thread(
            self.client.xadd,
            self._key(research_id),
            {"command": json.dumps(command, ensure_ascii=False)},
        )
        command["stream_id"] = str(stream_id)
        return command

    async def read(self, research_id: str, after_id: str) -> List[Tuple[str, Dict[str, Any]]]:
        rows = await asyncio.to_thread(
            self.client.xread,
            {self._key(research_id): after_id},
            count=100,
            block=1,
        )
        result: List[Tuple[str, Dict[str, Any]]] = []
        for _, messages in rows:
            for stream_id, fields in messages:
                result.append((str(stream_id), json.loads(fields["command"])))
        return result
