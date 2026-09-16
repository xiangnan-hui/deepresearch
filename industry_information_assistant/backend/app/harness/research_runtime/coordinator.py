"""协调 Fast API、后台执行器与现有 LangGraph Harness。"""

import asyncio
import logging
import time
import uuid
from typing import Any, Dict, Optional

from .command_bus import ResearchCommandBus
from .digest import ResearchDigestBuilder
from .event_bus import ResearchEventBus
from .fast_agent import FastResearchAgent
from .models import CommandType, InteractiveResearchState, ResearchStatus
from .state_store import ResearchStateStore

logger = logging.getLogger(__name__)

_PHASE_PROGRESS = {
    "planning": 5,
    "researching": 15,
    "re_researching": 35,
    "analyzing": 55,
    "writing": 70,
    "rewriting": 78,
    "revising": 88,
    "reviewing": 90,
}


class ResearchRuntime:
    """第一版进程内执行器；状态和通信均持久化到 Redis。"""

    def __init__(self):
        self.states = ResearchStateStore()
        self.events = ResearchEventBus()
        self.commands = ResearchCommandBus()
        self.digest_builder = ResearchDigestBuilder()
        self.fast_agent = FastResearchAgent(self.states, self.commands)
        self._tasks: Dict[str, asyncio.Task] = {}

    def is_active(self, research_id: str) -> bool:
        task = self._tasks.get(research_id)
        return bool(task and not task.done())

    async def start(
        self,
        *,
        query: str,
        session_id: str,
        kb_name: Optional[str] = None,
        search_web: bool = True,
        search_local: bool = False,
        user_id: Optional[str] = None,
        research_id: Optional[str] = None,
        resume: bool = False,
    ) -> Dict[str, Any]:
        research_id = research_id or f"research_{uuid.uuid4().hex}"
        if not resume:
            state = InteractiveResearchState(
                research_id=research_id,
                session_id=session_id,
                query=query,
                user_id=user_id,
                kb_name=kb_name,
                search_web=search_web,
                search_local=search_local,
            )
            await self.states.create(state)
            await self.events.publish(research_id, "queued", {"query": query, "session_id": session_id})
        task = self._tasks.get(research_id)
        if task and not task.done():
            return (await self.states.get(research_id)) or {}
        self._tasks[research_id] = asyncio.create_task(
            self._run(
                research_id=research_id,
                query=query,
                session_id=session_id,
                kb_name=kb_name,
                search_web=search_web,
                search_local=search_local,
                user_id=user_id,
                resume=resume,
            ),
            name=f"research-worker:{research_id}",
        )
        self._tasks[research_id].add_done_callback(lambda _: self._tasks.pop(research_id, None))
        return (await self.states.get(research_id)) or {}

    async def _run(self, **options: Any) -> None:
        research_id = options["research_id"]
        command_cursor = "0-0"
        run_started = time.perf_counter()
        phase_started = run_started
        active_phase = "starting"
        phase_durations: Dict[str, int] = {}
        review_iterations = 0
        try:
            await self.states.set_status(research_id, ResearchStatus.RUNNING.value, current_stage="starting")
            await self.events.publish(research_id, "started", {})

            # 延迟导入，避免 Runtime 与 DeepResearchService 初始化时循环依赖。
            try:
                from service.deep_research.service import DeepResearchService
            except ImportError:
                from app.service.deep_research.service import DeepResearchService

            while True:
                service = DeepResearchService()
                runtime_state = await self.states.get(research_id) or {}
                replan_requested = False
                async for event in service.harness.run(
                    options["query"],
                    options["session_id"],
                    resume=options.get("resume", False) and not runtime_state.get("user_constraints"),
                    user_id=options.get("user_id"),
                    kb_name=options.get("kb_name"),
                    search_web=options.get("search_web", True),
                    search_local=options.get("search_local", False),
                    research_id=research_id,
                    user_constraints=runtime_state.get("user_constraints", []),
                    plan_version=runtime_state.get("plan_version", 1),
                ):
                    if event.get("type") == "phase" and event.get("phase") != active_phase:
                        now = time.perf_counter()
                        phase_durations[active_phase] = phase_durations.get(active_phase, 0) + int((now - phase_started) * 1000)
                        active_phase = event.get("phase", "unknown")
                        if active_phase == "reviewing":
                            review_iterations += 1
                        phase_started = now
                    command_cursor, action = await self._safe_point(research_id, command_cursor)
                    if action == "cancel":
                        return
                    if action == "replan":
                        replan_requested = True
                        break
                    await self._handle_event(research_id, event)
                if not replan_requested:
                    break
                options["resume"] = False
                await self.states.update_progress(research_id, "planning", "impact_analysis", 3)
                await self.events.publish(research_id, "plan_updated", {
                    "plan_version": (await self.states.get(research_id) or {}).get("plan_version", 1),
                    "reason": "用户约束或研究方向发生变化，正在重新规划",
                })

            state = await self.states.get(research_id)
            if state and state.get("status") not in {
                ResearchStatus.CANCELLED.value,
                ResearchStatus.FAILED.value,
            }:
                now = time.perf_counter()
                phase_durations[active_phase] = phase_durations.get(active_phase, 0) + int((now - phase_started) * 1000)
                try:
                    from harness.model_gateway import summarize_model_metrics
                except ImportError:
                    from app.harness.model_gateway import summarize_model_metrics
                summary = summarize_model_metrics(research_id)
                summary.update({
                    "total_duration_ms": int((now - run_started) * 1000),
                    "phase_durations_ms": phase_durations,
                    "search_count": int(state.get("search_count", 0)),
                    "search_cache_hits": int(state.get("search_cache_hits", 0)),
                    "search_results_count": len(state.get("recent_search_results", [])),
                    "review_iterations": review_iterations,
                })
                await self.states.set_status(
                    research_id, ResearchStatus.COMPLETED.value, progress=100,
                    current_stage="completed", performance_summary=summary,
                )
                await self.events.publish(research_id, "performance_summary", summary)
                await self.events.publish(research_id, "completed", {"performance_summary": summary})
        except asyncio.CancelledError:
            await self.states.set_status(research_id, ResearchStatus.CANCELLED.value)
            await self.events.publish(research_id, "cancelled", {"reason": "runtime shutdown"})
            raise
        except Exception as exc:
            logger.exception("Research worker failed: %s", research_id)
            await self.states.set_status(research_id, ResearchStatus.FAILED.value, error=str(exc))
            await self.events.publish(research_id, "failed", {"error": str(exc)})

    async def _handle_event(self, research_id: str, event: Dict[str, Any]) -> None:
        event_type = event.get("type", "progress")
        await self.events.publish(research_id, event_type, event)
        state = await self.states.get(research_id)
        if not state:
            return
        if event_type == "phase":
            phase = event.get("phase", "")
            await self.states.update_progress(research_id, phase, phase, _PHASE_PROGRESS.get(phase, state.get("progress", 0)))
        elif event_type == "node_completed":
            await self.states.update(
                research_id,
                current_step=event.get("node", ""),
                checkpoint_id=event.get("checkpoint_id") or state.get("checkpoint_id"),
            )
            if event.get("checkpoint_id"):
                await self.events.publish(research_id, "checkpoint_created", {
                    "checkpoint_id": event["checkpoint_id"],
                    "node": event.get("node"),
                })
        elif event_type == "outline" and isinstance(event.get("content"), dict):
            await self.states.update(research_id, research_plan=event["content"].get("outline", []))
        elif event_type == "search_results" and isinstance(event.get("content"), dict):
            recent = list(state.get("recent_search_results", []))
            for result in event["content"].get("results", []):
                item = dict(result)
                item.setdefault("event_sequence", event.get("sequence"))
                if not any(old.get("url") == item.get("url") for old in recent):
                    recent.append(item)
            await self.states.update(research_id, recent_search_results=recent[-50:])
        elif event_type == "research_complete":
            await self.states.update(research_id, progress=100, current_stage="completed")
        elif event_type == "rag_sync":
            await self.states.update(research_id, rag_sync=event.get("content", {}))
        elif event_type == "error":
            await self.states.set_status(research_id, ResearchStatus.FAILED.value, error=str(event.get("content", "研究失败")))
        elif event_type == "search_metrics" and isinstance(event.get("content"), dict):
            await self.states.update(
                research_id,
                search_count=int(state.get("search_count", 0)) + int(event["content"].get("search_count", 0)),
                search_cache_hits=int(state.get("search_cache_hits", 0)) + int(event["content"].get("search_cache_hits", 0)),
            )
        elif event_type == "finding_tentative" and isinstance(event.get("content"), dict):
            findings = list(state.get("tentative_findings", []))
            finding = dict(event["content"])
            finding.setdefault("event_sequence", event.get("sequence"))
            finding.setdefault("plan_version", state.get("plan_version", 1))
            finding.setdefault("status", "active")
            if not any(item.get("id") == finding.get("id") for item in findings):
                findings.append(finding)
                await self.states.update(research_id, tentative_findings=findings)
        elif event_type == "finding_confirmed" and isinstance(event.get("content"), dict):
            confirmed = list(state.get("confirmed_findings", []))
            tentative = [item for item in state.get("tentative_findings", []) if item.get("id") != event["content"].get("id")]
            finding = dict(event["content"])
            finding.setdefault("event_sequence", event.get("sequence"))
            finding.setdefault("plan_version", state.get("plan_version", 1))
            finding.setdefault("status", "active")
            if not any(item.get("id") == finding.get("id") for item in confirmed):
                confirmed.append(finding)
            await self.states.update(research_id, confirmed_findings=confirmed, tentative_findings=tentative)

        current = (await self.states.get(research_id)) or state
        digest = self.digest_builder.update(current.get("research_digest", {}), event)
        await self.states.update_digest(research_id, digest)

    async def _safe_point(self, research_id: str, cursor: str) -> tuple[str, Optional[str]]:
        for stream_id, command in await self.commands.read(research_id, cursor):
            cursor = stream_id
            current_state = await self.states.get(research_id) or {}
            receipts = dict(current_state.get("command_receipts", {}))
            command_id = str(command.get("command_id") or stream_id)
            if command_id in receipts and receipts[command_id].get("status") == "applied":
                continue
            receipts[command_id] = {"status": "accepted", "stream_id": stream_id}
            await self.states.update(research_id, command_receipts=receipts, command_cursor=cursor)
            await self.events.publish(research_id, "command_accepted", {"command_id": command_id})
            command_type = command.get("type")
            payload = command.get("payload") or {}
            if command_type == CommandType.CANCEL.value:
                receipts[command_id]["status"] = "applied"
                await self.states.update(research_id, command_receipts=receipts)
                await self.states.set_status(research_id, ResearchStatus.CANCELLED.value)
                await self.events.publish(research_id, "cancelled", {"command_id": command.get("command_id")})
                return cursor, "cancel"
            if command_type == CommandType.PAUSE.value:
                await self.states.set_status(research_id, ResearchStatus.PAUSED.value)
                await self.events.publish(research_id, "paused", {"command_id": command.get("command_id")})
                while True:
                    await asyncio.sleep(0.5)
                    resume_commands = await self.commands.read(research_id, cursor)
                    if not resume_commands:
                        continue
                    for resume_id, resume_command in resume_commands:
                        cursor = resume_id
                        if resume_command.get("type") == CommandType.CANCEL.value:
                            await self.states.set_status(research_id, ResearchStatus.CANCELLED.value)
                            await self.events.publish(research_id, "cancelled", {})
                            return cursor, "cancel"
                        if resume_command.get("type") == CommandType.RESUME.value:
                            await self.states.set_status(research_id, ResearchStatus.RUNNING.value)
                            await self.events.publish(research_id, "resumed", {})
                            break
                    else:
                        continue
                    break
            elif command_type in {CommandType.ADD_CONSTRAINT.value, CommandType.CHANGE_DIRECTION.value}:
                current = await self.states.get(research_id) or {}
                constraints = list(current.get("user_constraints", []))
                value = payload.get("constraint") or payload.get("direction")
                if value:
                    constraints.append(str(value))
                await self.states.update(
                    research_id,
                    user_constraints=constraints,
                    plan_version=int(current.get("plan_version", 1)) + 1,
                    confirmed_findings=[
                        {**item, "status": "invalidated"}
                        for item in current.get("confirmed_findings", [])
                    ],
                    tentative_findings=[
                        {**item, "status": "invalidated"}
                        for item in current.get("tentative_findings", [])
                    ],
                )
                await self.events.publish(research_id, "plan_update_requested", command)
                receipts[command_id]["status"] = "applied"
                await self.states.update(research_id, command_receipts=receipts)
                return cursor, "replan"
            elif command_type in {CommandType.ADD_QUESTION.value, CommandType.PRIORITIZE_GAP.value}:
                current = await self.states.get(research_id) or {}
                gaps = list(current.get("remaining_gaps", []))
                value = payload.get("question") or payload.get("gap")
                if value:
                    gaps.append(str(value))
                await self.states.update(research_id, remaining_gaps=gaps)
                await self.events.publish(research_id, "gap_discovered", command)
            receipts[command_id]["status"] = "applied"
            await self.states.update(research_id, command_receipts=receipts)
            await self.events.publish(research_id, "command_applied", {"command_id": command_id})
        return cursor, None

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)


_runtime: Optional[ResearchRuntime] = None


def get_research_runtime() -> ResearchRuntime:
    global _runtime
    if _runtime is None:
        _runtime = ResearchRuntime()
    return _runtime
