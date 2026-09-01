import asyncio
import unittest
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict

from harness.context import FreshnessPolicy, RunContext
from harness.evaluator import FreshnessEvaluator
from harness.runtime import ResearchHarness
from harness.skills import FreshResearchSkill


class FakeWorkflow:
    async def run(self, query: str, session_id: str, **kwargs: Any) -> AsyncGenerator[Dict[str, Any], None]:
        yield {"type": "phase", "phase": "planning"}
        yield {"type": "research_complete", "final_report": "ok"}

    async def run_sync(self, query: str, session_id: str, **kwargs: Any) -> Dict[str, Any]:
        return {"query": query, "session_id": session_id, "run_context": kwargs["run_context"]}


class HarnessTests(unittest.TestCase):
    def test_latest_query_enables_freshness_policy(self) -> None:
        policy = FreshnessPolicy.from_query("主流模型的最新差异是什么？")
        self.assertTrue(policy.required)
        self.assertEqual(policy.search_freshness, "oneYear")

    def test_ordinary_query_has_no_date_filter(self) -> None:
        policy = FreshnessPolicy.from_query("解释 Transformer 的注意力机制")
        self.assertFalse(policy.required)
        self.assertEqual(policy.search_freshness, "noLimit")

    def test_runtime_wraps_legacy_events(self) -> None:
        async def collect() -> list[Dict[str, Any]]:
            harness = ResearchHarness(FakeWorkflow(), model="test-model")
            return [event async for event in harness.run("最新模型", "session-1")]

        events = asyncio.run(collect())
        self.assertEqual([event["sequence"] for event in events], [1, 2])
        self.assertTrue(all(event["run_id"].startswith("run_") for event in events))
        self.assertTrue(all(event["session_id"] == "session-1" for event in events))

    def test_fresh_research_skill_adds_current_year(self) -> None:
        context = RunContext.create(
            run_id="run-test",
            session_id="session-test",
            query="最新模型",
        ).to_dict()
        query = FreshResearchSkill.decorate_query("推理模型比较", context)
        self.assertIn(str(datetime.now().year), query)

    def test_freshness_evaluator_uses_publication_date(self) -> None:
        now = datetime.now()
        context = RunContext.create(
            run_id="run-test",
            session_id="session-test",
            query="最新模型",
        ).to_dict()
        state = {
            "run_context": context,
            "raw_sources": [
                {
                    "url": f"https://example.com/{index}",
                    "published_at": (now - timedelta(days=index)).isoformat(),
                }
                for index in range(3)
            ],
        }
        result = FreshnessEvaluator().evaluate(state)
        self.assertTrue(result["passed"])
        self.assertEqual(result["recent_sources"], 3)


if __name__ == "__main__":
    unittest.main()
