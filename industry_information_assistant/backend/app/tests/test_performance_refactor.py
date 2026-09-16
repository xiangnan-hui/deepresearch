import asyncio
import re
import unittest
from types import SimpleNamespace

from harness.model_gateway import ModelGateway, get_model_metrics, reset_model_context, set_model_context

from service.deep_research.chart_builder import ChartBuilder, build_knowledge_graph
from service.deep_research.evidence import EvidenceAdapter
from service.deep_research.quality_gate import DeterministicQualityGate
from service.deep_research.state import ResearchPhase, create_initial_state
from service.deep_research.agents.data_analyst import DataAnalyst
from service.deep_research.agents.architect import ChiefArchitect
from service.deep_research.agents.critic import CriticMaster
from service.deep_research.agents.scout import DeepScout
from service.deep_research.agents import scout as scout_module
from service.deep_research.agents.writer import LeadWriter
from service.deep_research.agents.wizard import CodeWizard
from service.deep_research.graph import DeepResearchGraph


def state_with_evidence():
    state = create_initial_state("AI 趋势", "session-test")
    state["research_id"] = "research-test"
    state["outline"] = [{"id": "sec_1", "title": "趋势", "description": "趋势", "status": "pending"}]
    state["facts"] = [{
        "id": "ev_1", "evidence_id": "ev_1", "content": "指标增长到 10",
        "source_url": "https://example.com/a", "source_name": "Example",
        "related_sections": ["sec_1"], "credibility_score": 0.8,
    }]
    return state


class PerformanceRefactorTests(unittest.TestCase):
    def test_common_path_includes_editorial_pass(self):
        async def run():
            scout_module.MILVUS_AVAILABLE = False
            graph = DeepResearchGraph(
                llm_api_key="test", llm_base_url="https://example.com/v1",
                deepscout_api_key="test", deepscout_base_url="https://example.com/v1",
                search_api_key="test", model="test", max_iterations=1,
            )
            graph.checkpoint_service = None
            calls = []

            async def fake_llm(agent_name, **kwargs):
                calls.append((agent_name, kwargs.get("operation_name", "complete")))
                if agent_name == "ChiefArchitect":
                    return '{"outline":[' + ",".join(
                        f'{{"id":"sec_{i}","title":"章节{i}","description":"说明{i}","search_queries":["查询{i}"]}}'
                        for i in range(1, 4)
                    ) + '],"research_questions":["问题"],"key_entities":[]}'
                if agent_name == "DataAnalyst":
                    return '{"data_points":[],"time_series":[],"distributions":[],"facts":[],"entities":[],"relations":[],"insights":[]}'
                if agent_name == "LeadWriter":
                    ids = re.findall(r"\[(ev_[^\]]+)\]", kwargs.get("user_prompt", ""))
                    evidence_id = ids[0] if ids else "ev_unknown"
                    return '{"content":"基于已有证据 [' + evidence_id + ']","key_points":[],"citations":[]}'
                if agent_name == "CriticMaster":
                    return '{"overall_assessment":{"verdict":"pass","quality_score":9,"summary":"ok"},"issues":[],"missing_aspects":[],"fact_check_results":[]}'
                raise AssertionError(f"unexpected model call: {agent_name}")

            for agent in (graph.architect, graph.scout, graph.data_analyst, graph.writer, graph.critic, graph.wizard):
                async def bound(agent=agent, **kwargs):
                    return await fake_llm(agent.name, **kwargs)
                agent.call_llm = bound

            async def fake_search(query, count=10, freshness="noLimit"):
                number = query[-1] if query[-1].isdigit() else "1"
                return [{"url": f"https://example.com/{number}", "title": f"来源{number}", "site_name": "Example", "summary": f"章节{number}事实", "date": "2026-09-01"}]

            graph.scout._execute_search = fake_search
            state = await graph.run_sync("AI 趋势", "session-e2e")
            return calls, state

        calls, state = asyncio.run(run())
        self.assertEqual(len(calls), 7)
        self.assertEqual([name for name, _ in calls].count("LeadWriter"), 4)
        self.assertEqual(state["phase"], ResearchPhase.COMPLETED.value)

    def test_model_gateway_records_usage_and_cache_hits(self):
        calls = []

        def create(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=SimpleNamespace(prompt_tokens=11, completion_tokens=3),
            )

        gateway = ModelGateway.__new__(ModelGateway)
        gateway.model = "fake-model"
        gateway.client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

        async def run():
            token = set_model_context(research_id="metrics-test", session_id="s1")
            try:
                args = {"messages": [{"role": "user", "content": "unique-metrics-test"}]}
                await gateway.complete(metric_context={"agent_name": "Test", "operation_name": "measure"}, **args)
                await gateway.complete(metric_context={"agent_name": "Test", "operation_name": "measure"}, **args)
            finally:
                reset_model_context(token)

        asyncio.run(run())
        rows = get_model_metrics("metrics-test", clear=True)
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(sum(row["output_tokens"] for row in rows), 3)
        self.assertTrue(rows[-1]["cache_hit"])

    def test_evidence_adapter_deduplicates_tool_results(self):
        rows = EvidenceAdapter.normalize_many([
            {"url": "HTTPS://EXAMPLE.COM/a/", "summary": "A", "title": "One"},
            {"url": "https://example.com/a", "summary": "A", "title": "One"},
        ])
        self.assertEqual(len(rows), 1)
        self.assertTrue(rows[0]["evidence_id"].startswith("ev_"))

    def test_chart_and_graph_are_deterministic_without_llm(self):
        extracted = {
            "time_series": [{"metric": "规模", "unit": "亿元", "data": [{"year": 2025, "value": 1}, {"year": 2026, "value": 2}]}],
            "entities": [{"id": "a", "name": "A", "type": "company", "importance": 8}],
            "relations": [],
        }
        self.assertEqual(ChartBuilder.build(extracted)[0]["type"], "line")
        self.assertEqual(build_knowledge_graph(extracted)["nodes"][0]["size"], 44)

    def test_chart_and_graph_have_evidence_fallbacks(self):
        evidence = [{
            "id": "ev_1", "content": "OpenAI市场份额达到35.2%，Anthropic支持率为83.2%",
            "credibility_score": 0.8,
        }]
        charts = ChartBuilder.build({}, evidence)
        graph = build_knowledge_graph({}, evidence, "AI前沿进展")
        self.assertEqual(len(charts), 1)
        self.assertGreaterEqual(len(graph["nodes"]), 3)
        self.assertGreaterEqual(len(graph["edges"]), 2)

    def test_data_analyst_executes_exactly_one_model_call(self):
        async def run():
            state = state_with_evidence()
            state["phase"] = ResearchPhase.ANALYZING.value
            state["facts"] = [
                {"id": "ev_1", "evidence_id": "ev_1", "content": "OpenAI份额35.2%", "source_url": "https://example.com/1", "source_name": "A", "related_sections": ["sec_1"], "credibility_score": 0.8},
                {"id": "ev_2", "evidence_id": "ev_2", "content": "Anthropic支持率83.2%", "source_url": "https://example.com/2", "source_name": "B", "related_sections": ["sec_1"], "credibility_score": 0.8},
            ]
            agent = DataAnalyst("test", "https://example.com/v1", "test")
            calls = []
            events = []

            async def fake_call(**kwargs):
                calls.append(kwargs)
                return '{"data_points":[],"time_series":[],"distributions":[],"facts":[],"entities":[],"relations":[],"insights":[]}'

            agent.call_llm = fake_call
            agent.add_message = lambda _state, event_type, content: events.append(event_type)
            await agent.process(state)
            return calls, events, state

        calls, events, state = asyncio.run(run())
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["operation_name"], "extract_facts_data_entities")
        self.assertIn("knowledge_graph", events)
        self.assertIn("charts", events)
        self.assertGreater(len(state["knowledge_graph"]["nodes"]), 1)
        self.assertGreater(len(state["charts"]), 0)

    def test_architect_parse_failure_uses_local_fallback_without_retry(self):
        async def run():
            state = create_initial_state("AI 趋势", "session-test")
            agent = ChiefArchitect("test", "https://example.com/v1", "test")
            calls = []

            async def fake_call(**kwargs):
                calls.append(kwargs)
                return "{}"

            agent.call_llm = fake_call
            await agent.process(state)
            return calls, state

        calls, state = asyncio.run(run())
        self.assertEqual(len(calls), 1)
        self.assertEqual(len(state["outline"]), 3)

    def test_scout_tool_adapter_requires_no_model_call(self):
        result = DeepScout._adapt_search_results([
            {"url": "https://example.com/a", "title": "A", "summary": "事实 A", "site_name": "Example"}
        ], "sec_1")
        self.assertEqual(len(result["extracted_facts"]), 1)
        self.assertEqual(result["extracted_facts"][0]["related_sections"], ["sec_1"])

    def test_writer_edits_whole_report_after_sections(self):
        async def run():
            state = state_with_evidence()
            state["phase"] = ResearchPhase.WRITING.value
            agent = LeadWriter("test", "https://example.com/v1", "test")
            calls = []
            events = []

            async def fake_call(**kwargs):
                calls.append(kwargs)
                return "# AI 趋势\n\n## 趋势\n证据支持的结论 [ev_1]"

            agent.call_llm = fake_call
            agent.add_message = lambda _state, event_type, content: events.append(event_type)
            await agent.process(state)
            return calls, state, events

        calls, state, events = asyncio.run(run())
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1]["operation_name"], "polish_report")
        self.assertTrue(calls[0]["json_mode"])
        self.assertEqual(calls[0]["operation_name"], "write_section")
        self.assertIn("趋势", state["draft_sections"]["sec_1"])
        self.assertIn("section_content", events)
        self.assertIn("report_draft", events)

    def test_common_work_skips_code_wizard(self):
        state = state_with_evidence()
        state["data_points"] = [{"value": 1}, {"value": 2}, {"value": 3}]
        self.assertFalse(CodeWizard._requires_complex_analysis(state))
        state["query"] = "使用回归预测未来趋势"
        self.assertTrue(CodeWizard._requires_complex_analysis(state))

    def test_quality_gate_fails_before_semantic_review(self):
        state = state_with_evidence()
        state["final_report"] = ""
        result = DeterministicQualityGate.evaluate(state)
        self.assertFalse(result["passed"])
        self.assertIn(result["verdict"], {"REVISE", "RESEARCH"})

    def test_critic_rechecks_after_revision(self):
        async def run():
            state = create_initial_state("AI 趋势", "session-test")
            state["phase"] = ResearchPhase.REVIEWING.value
            state["outline"] = [
                {"id": f"sec_{i}", "title": f"章节{i}", "status": "drafted"} for i in range(1, 4)
            ]
            state["facts"] = [
                {"id": f"ev_{i}", "evidence_id": f"ev_{i}", "source_url": f"https://example.com/{i}", "content": "事实", "related_sections": [f"sec_{i}"]}
                for i in range(1, 4)
            ]
            state["final_report"] = "\n".join(f"## 章节{i}\n内容 [ev_{i}]" for i in range(1, 4))
            agent = CriticMaster("test", "https://example.com/v1", "test")
            calls = []

            async def fake_review(_state):
                calls.append(1)
                return {"overall_assessment": {"verdict": "pass", "quality_score": 9, "summary": "ok"}, "issues": [], "missing_aspects": [], "fact_check_results": []}

            agent._review_content = fake_review
            await agent.process(state)
            state["phase"] = ResearchPhase.REVIEWING.value
            await agent.process(state)
            return calls

        self.assertEqual(len(asyncio.run(run())), 2)


if __name__ == "__main__":
    unittest.main()
