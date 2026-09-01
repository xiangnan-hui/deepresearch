"""Harness runtime around the LangGraph research workflow."""

import uuid
from typing import Any, AsyncGenerator, Dict, Optional, Protocol

from .context import RunContext
from .events import HarnessEvent
from .registry import SkillRegistry, ToolRegistry
from .skills import FreshResearchSkill


class ResearchWorkflow(Protocol):
    async def run(self, query: str, session_id: str, **kwargs: Any) -> AsyncGenerator[Dict[str, Any], None]: ...

    async def run_sync(self, query: str, session_id: str, **kwargs: Any) -> Dict[str, Any]: ...


class ResearchHarness:
    """Creates run context and normalizes all workflow events."""

    def __init__(self, workflow: ResearchWorkflow, model: Optional[str] = None):
        self.workflow = workflow
        self.model = model
        self.tools = ToolRegistry()
        self.skills = SkillRegistry()
        self.skills.register(FreshResearchSkill.name, FreshResearchSkill())

    def create_context(self, query: str, session_id: str, user_id: Optional[str] = None) -> RunContext:
        return RunContext.create(
            run_id=f"run_{uuid.uuid4().hex}",
            session_id=session_id,
            query=query,
            user_id=user_id,
            model=self.model,
        )

    async def run(self, query: str, session_id: str, **kwargs: Any) -> AsyncGenerator[Dict[str, Any], None]:
        context = self.create_context(query, session_id, kwargs.get("user_id"))
        sequence = 0
        async for event in self.workflow.run(query, session_id, run_context=context.to_dict(), **kwargs):
            sequence += 1
            yield HarnessEvent.wrap(
                event,
                run_id=context.run_id,
                session_id=session_id,
                sequence=sequence,
            )

    async def run_sync(self, query: str, session_id: str, **kwargs: Any) -> Dict[str, Any]:
        context = self.create_context(query, session_id, kwargs.get("user_id"))
        return await self.workflow.run_sync(query, session_id, run_context=context.to_dict(), **kwargs)
