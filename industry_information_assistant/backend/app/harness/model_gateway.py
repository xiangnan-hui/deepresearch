"""Central model invocation boundary for agents."""

import asyncio
import logging
from typing import Any, Dict

from openai import OpenAI

logger = logging.getLogger("Harness.ModelGateway")


class ModelGateway:
    """Owns model client construction and asynchronous completion calls."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    async def complete(self, **kwargs: Any) -> Any:
        request: Dict[str, Any] = dict(kwargs)
        request.setdefault("model", self.model)
        return await asyncio.to_thread(self.client.chat.completions.create, **request)
