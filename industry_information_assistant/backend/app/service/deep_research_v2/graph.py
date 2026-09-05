
"""
DeepResearch V2.0 - LangGraph 工作流

实现多智能体协作的状态机图：
Plan -> Research -> Analyze -> Write -> Review -> (Revise) -> Complete

使用 LangGraph 实现循环和条件分支。
"""

import logging
from typing import Dict, Any, List, Literal, AsyncGenerator
from datetime import datetime

# LangGraph 导入 - 如果没有安装则使用简化版本
try:
    from langgraph.graph import StateGraph, END
    LANGGRAPH_AVAILABLE = True
except ImportError:
    LANGGRAPH_AVAILABLE = False

try:
    from langgraph.types import StreamWriter
    from langgraph.config import var_child_runnable_config
    from langchain_core.runnables import RunnableConfig
except ImportError:
    StreamWriter = Any
    RunnableConfig = Dict[str, Any]
    var_child_runnable_config = None

if not LANGGRAPH_AVAILABLE:
    logging.warning("LangGraph not installed. Using simplified workflow.")

from .state import ResearchState, ResearchPhase, create_initial_state
from .agents import ChiefArchitect, DeepScout, CodeWizard, CriticMaster, LeadWriter, DataAnalyst
try:
    from harness.evaluator import FreshnessEvaluator
except ImportError:
    from app.harness.evaluator import FreshnessEvaluator

# 导入检查点服务
try:
    from service.checkpoint_service import get_checkpoint_service
except ImportError:
    try:
        from app.service.checkpoint_service import get_checkpoint_service
    except ImportError:
        # 兼容直接运行脚本的情况
        def get_checkpoint_service():
            return None

# 导入配置
try:
    from config.llm_config import get_config
except ImportError:
    try:
        from app.config.llm_config import get_config
    except ImportError:
        # 兼容直接运行脚本的情况
        import sys
        import os
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        from config.llm_config import get_config

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger("DeepResearchGraph")


class DeepResearchGraph:
    """
    DeepResearch V2.0 工作流图

    实现完整的多智能体协作流程：
    1. Plan (ChiefArchitect) - 分析问题，生成研究大纲
    2. Research (DeepScout) - 并行深度搜索
    3. Analyze (CodeWizard) - 数据分析和可视化
    4. Write (LeadWriter) - 撰写报告
    5. Review (CriticMaster) - 对抗式审核
    6. Revise (LeadWriter) - 修订（如果需要）
    """

    def __init__(
        self,
        llm_api_key: str = None,
        llm_base_url: str = None,
        search_api_key: str = None,
        model: str = None,
        max_iterations: int = None,
        deepscout_api_key: str = None,
        deepscout_base_url: str = None
    ):
        """
        初始化工作流

        所有参数都可从配置文件读取，传入的参数会覆盖配置。
        5 个核心 Agent（ChiefArchitect/DataAnalyst/CodeWizard/LeadWriter/CriticMaster）
        使用 DeepSeek V4 配置（llm_api_key/llm_base_url），
        DeepScout 使用独立的 DEEPSCOUT_API_KEY / DEEPSCOUT_BASE_URL 配置。
        """
        # 获取配置
        config = get_config()

        # 使用传入参数或配置默认值（5 个核心 Agent -> DeepSeek）
        self.llm_api_key = llm_api_key or config.api_key
        self.llm_base_url = llm_base_url or config.base_url
        # DeepScout 独立配置（glm-5.2）
        self.deepscout_api_key = deepscout_api_key or config.deepscout_api_key
        self.deepscout_base_url = deepscout_base_url or config.deepscout_base_url
        self.search_api_key = search_api_key or config.search_api_key
        self.model = model or config.default_model
        self.max_iterations = max_iterations or config.research.max_iterations

        # 初始化各个 Agent（使用各自配置的模型）
        self.architect = ChiefArchitect(
            self.llm_api_key, self.llm_base_url,
            config.agents.architect.model
        )
        self.scout = DeepScout(
            self.deepscout_api_key, self.deepscout_base_url, self.search_api_key,
            config.agents.scout.model
        )
        self.data_analyst = DataAnalyst(
            self.llm_api_key, self.llm_base_url,
            config.agents.data_analyst.model
        )
        self.wizard = CodeWizard(
            self.llm_api_key, self.llm_base_url,
            config.agents.wizard.model
        )
        self.critic = CriticMaster(
            self.llm_api_key, self.llm_base_url,
            config.agents.critic.model
        )
        self.writer = LeadWriter(
            self.llm_api_key, self.llm_base_url,
            config.agents.writer.model
        )

        logger.info(f"DeepResearchGraph initialized with models:")
        logger.info(f"  - Architect: {config.agents.architect.model}")
        logger.info(f"  - Scout: {config.agents.scout.model}")
        logger.info(f"  - DataAnalyst: {config.agents.data_analyst.model}")
        logger.info(f"  - Wizard: {config.agents.wizard.model}")
        logger.info(f"  - Critic: {config.agents.critic.model}")
        logger.info(f"  - Writer: {config.agents.writer.model}")

        # 检查点服务
        self.checkpoint_service = get_checkpoint_service()
        self.freshness_evaluator = FreshnessEvaluator()

        # 构建图
        if LANGGRAPH_AVAILABLE:
            self.graph = self._build_langgraph()
        else:
            self.graph = None

    def _save_checkpoint(
        self,
        state: Dict[str, Any],
        user_id: str = None,
        ui_state: Dict[str, Any] = None
    ) -> str:
        """保存检查点（包含后端状态和 UI 状态）"""
        if not self.checkpoint_service:
            return ""

        session_id = state.get("session_id", "")
        if not session_id:
            return ""

        try:
            checkpoint_id = self.checkpoint_service.save_checkpoint(
                session_id=session_id,
                state=state,
                user_id=user_id,
                ui_state=ui_state,
                final_report=state.get("final_report")
            )
            if checkpoint_id:
                logger.info(f"Checkpoint saved: {checkpoint_id}")
                return checkpoint_id
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")

        return ""

    def _load_checkpoint(self, session_id: str) -> Dict[str, Any]:
        """加载检查点"""
        if not self.checkpoint_service:
            return None

        try:
            state = self.checkpoint_service.load_checkpoint(session_id)
            if state:
                logger.info(f"Checkpoint loaded for session: {session_id}")
                return state
        except Exception as e:
            logger.warning(f"Failed to load checkpoint: {e}")

        return None

    def get_checkpoint_info(self, session_id: str) -> Dict[str, Any]:
        """获取检查点信息"""
        if not self.checkpoint_service:
            return None
        return self.checkpoint_service.get_checkpoint_info(session_id)

    def _build_langgraph(self):
        """构建 LangGraph 状态图"""
        # 定义图
        workflow = StateGraph(ResearchState)

        # 添加节点
        workflow.add_node("plan", self._plan_node)
        workflow.add_node("research", self._research_node)
        workflow.add_node("data_analyze", self._data_analyze_node)
        workflow.add_node("analyze", self._analyze_node)
        workflow.add_node("write", self._write_node)
        workflow.add_node("review", self._review_node)
        workflow.add_node("re_research", self._re_research_node)
        workflow.add_node("rewrite", self._rewrite_node)
        workflow.add_node("revise", self._revise_node)

        # 设置入口
        workflow.set_entry_point("plan")

        # 添加边
        workflow.add_edge("plan", "research")
        workflow.add_edge("research", "data_analyze")
        workflow.add_edge("data_analyze", "analyze")
        workflow.add_edge("analyze", "write")
        workflow.add_edge("write", "review")

        # 条件边：审核后决定下一步
        workflow.add_conditional_edges(
            "review",
            self._route_after_review,
            {
                "re_research": "re_research",
                "revise": "revise",
                "complete": END
            }
        )

        workflow.add_edge("re_research", "rewrite")
        workflow.add_edge("rewrite", "review")
        # 修订后回到审核
        workflow.add_edge("revise", "review")

        return workflow.compile()

    async def _run_agent_node(
        self,
        state: ResearchState,
        writer: StreamWriter,
        config: RunnableConfig,
        agent: Any,
        phase: ResearchPhase,
        phase_name: str,
        phase_content: str,
    ) -> Dict[str, Any]:
        """在 LangGraph 节点中执行 Agent，并转发节点内部 custom 事件。"""
        # Python 3.10 的异步任务不会自动保留 LangGraph runnable context；
        # 显式绑定 config 后，StreamWriter 才能在长节点内部持续发送事件。
        context_token = var_child_runnable_config.set(config)
        try:
            from harness.model_gateway import set_model_context, reset_model_context
        except ImportError:
            from app.harness.model_gateway import set_model_context, reset_model_context
        model_context_token = set_model_context(
            research_id=state.get("research_id", ""),
            session_id=state.get("session_id", ""),
        )
        try:
            state = dict(state)
            state["phase"] = phase.value
            state["_stream_writer"] = writer
            writer({"type": "phase", "phase": phase_name, "content": phase_content})
            result = dict(await agent.process(state))
        finally:
            state.pop("_stream_writer", None)
            reset_model_context(model_context_token)
            var_child_runnable_config.reset(context_token)
        result.pop("_stream_writer", None)
        return result

    async def _plan_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """规划节点"""
        logger.info("Executing Plan node...")
        return await self._run_agent_node(
            state, writer, config, self.architect, ResearchPhase.INIT,
            "planning", "开始规划研究..."
        )

    async def _research_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """研究节点"""
        logger.info("Executing Research node...")
        return await self._run_agent_node(
            state, writer, config, self.scout, ResearchPhase.RESEARCHING,
            "researching", "开始深度搜索..."
        )

    async def _data_analyze_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """数据分析节点"""
        logger.info("Executing DataAnalyze node...")
        return await self._run_agent_node(
            state, writer, config, self.data_analyst, ResearchPhase.ANALYZING,
            "analyzing", "开始数据分析..."
        )

    async def _analyze_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """分析节点"""
        logger.info("Executing Analyze node...")
        return await self._run_agent_node(
            state, writer, config, self.wizard, ResearchPhase.ANALYZING,
            "analyzing", "生成数据分析与可视化..."
        )

    async def _write_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """写作节点"""
        logger.info("Executing Write node...")
        return await self._run_agent_node(
            state, writer, config, self.writer, ResearchPhase.WRITING,
            "writing", "开始撰写报告..."
        )

    async def _review_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """审核节点"""
        logger.info("Executing Review node...")
        return await self._run_agent_node(
            state, writer, config, self.critic, ResearchPhase.REVIEWING,
            "reviewing", f"审核中（第 {state.get('iteration', 0) + 1} 轮）..."
        )

    async def _re_research_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """根据审核反馈补充搜索。"""
        logger.info("Executing ReResearch node...")
        return await self._run_agent_node(
            state, writer, config, self.scout, ResearchPhase.RE_RESEARCHING,
            "re_researching", "根据审核反馈补充搜索..."
        )

    async def _rewrite_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """补充搜索后重新撰写。"""
        logger.info("Executing Rewrite node...")
        return await self._run_agent_node(
            state, writer, config, self.writer, ResearchPhase.WRITING,
            "rewriting", "基于新信息重新撰写..."
        )

    async def _revise_node(self, state: ResearchState, writer: StreamWriter, config: RunnableConfig) -> Dict[str, Any]:
        """修订节点"""
        logger.info("Executing Revise node...")
        return await self._run_agent_node(
            state, writer, config, self.writer, ResearchPhase.REVISING,
            "revising", "根据反馈修订报告..."
        )

    def _route_after_review(self, state: ResearchState) -> Literal["re_research", "revise", "complete"]:
        """根据 Critic 写入的阶段决定审核后的图路由。"""
        if state.get("phase") == ResearchPhase.RE_RESEARCHING.value:
            return "re_research"
        if state.get("phase") == ResearchPhase.REVISING.value:
            return "revise"
        return "complete"

    async def run(
        self,
        query: str,
        session_id: str,
        resume: bool = False,
        user_id: str = None,
        search_web: bool = True,
        search_local: bool = False,
        run_context: Dict[str, Any] = None,
        research_id: str = "",
        user_constraints: List[str] = None,
        plan_version: int = 1,
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        执行研究流程（流式输出）

        Args:
            query: 用户问题
            session_id: 会话ID
            resume: 是否从检查点恢复
            user_id: 用户ID（用于检查点）
            search_web: 是否启用网络搜索（默认True）
            search_local: 是否启用本地知识库搜索（默认False）

        Yields:
            SSE 事件字典
        """
        # 尝试从检查点恢复
        state = None
        if resume and session_id:
            state = self._load_checkpoint(session_id)
            if state:
                yield {
                    "type": "research_resumed",
                    "phase": state.get("phase", ""),
                    "session_id": session_id,
                    "timestamp": datetime.now().isoformat()
                }

        # 如果没有检查点，创建初始状态
        if not state:
            state = create_initial_state(
                query, session_id,
                search_web=search_web,
                search_local=search_local
            )
            state["max_iterations"] = self.max_iterations

            yield {
                "type": "research_start",
                "query": query,
                "session_id": session_id,
                "search_web": search_web,
                "search_local": search_local,
                "timestamp": datetime.now().isoformat()
            }

        if research_id:
            state["research_id"] = research_id
        state["user_constraints"] = list(user_constraints or state.get("user_constraints", []))
        state["plan_version"] = plan_version

        # Harness context belongs to the run, not to an individual Agent.
        # On resume, the new context refreshes current_time while retaining graph state.
        if run_context:
            state["run_context"] = run_context

        # 存储 user_id 用于检查点
        state["_user_id"] = user_id

        if not LANGGRAPH_AVAILABLE or self.graph is None or StreamWriter is Any:
            yield {
                "type": "error",
                "content": "当前环境的 LangGraph 版本不支持节点内 custom streaming，请安装项目要求的 LangGraph 版本"
            }
            return

        # v2 主流程完全由 LangGraph 调度；节点内部事件通过 custom stream 实时输出。
        async for event in self._run_with_langgraph(state):
            yield event

    async def _run_with_langgraph(self, state: ResearchState) -> AsyncGenerator[Dict[str, Any], None]:
        """使用 LangGraph 执行，并转发节点内部 custom 事件。"""
        session_id = state.get("session_id", "")
        try:
            # custom: Agent.add_message() 的实时事件
            # updates: 节点完成后的状态更新
            async for chunk in self.graph.astream(
                state,
                stream_mode=["custom", "updates"],
            ):
                # 不同 LangGraph 版本分别返回 (mode, data) 或
                # (namespace, mode, data)，统一归一化。
                if not isinstance(chunk, tuple):
                    continue
                if len(chunk) == 2:
                    mode, payload = chunk
                elif len(chunk) == 3:
                    _, mode, payload = chunk
                else:
                    logger.warning(f"Unknown LangGraph stream chunk: {chunk!r}")
                    continue
                if mode == "custom":
                    yield payload
                    continue

                if mode == "updates" and isinstance(payload, dict):
                    for node_name, node_state in payload.items():
                        if not isinstance(node_state, dict):
                            continue
                        state.update(node_state)
                        checkpoint_id = self._save_checkpoint(state, user_id=state.get("_user_id"))
                        # 对前端暴露统一的节点完成事件，不传输完整 state。
                        yield {
                            "type": "node_completed",
                            "node": node_name,
                            "phase": node_state.get("phase", ""),
                            "session_id": session_id,
                            "checkpoint_id": checkpoint_id or None,
                        }

            freshness_result = self.freshness_evaluator.evaluate(state)
            state.setdefault("quality_gates", {})["freshness"] = freshness_result
            state["phase"] = ResearchPhase.COMPLETED.value
            self._save_checkpoint(state, user_id=state.get("_user_id"))
            if self.checkpoint_service and session_id:
                self.checkpoint_service.update_status(session_id, "completed")
            if freshness_result.get("required") and not freshness_result.get("passed"):
                yield {
                    "type": "quality_warning",
                    "quality_gate": "freshness",
                    "content": "最新信息来源不足，报告可能包含较旧资料",
                    "details": freshness_result,
                }

            # 保持与旧 SSE 协议兼容：图执行结束后发送统一完成事件。
            yield {
                "type": "research_complete",
                "final_report": state.get("final_report", ""),
                "quality_score": state.get("quality_score", 0.0),
                "facts_count": len(state.get("facts", [])),
                "charts_count": len(state.get("charts", [])),
                "iterations": state.get("iteration", 0),
                "quality_gates": state.get("quality_gates", {}),
            }

        except Exception as e:
            logger.error(f"LangGraph execution error: {e}")
            if self.checkpoint_service and session_id:
                self.checkpoint_service.update_status(session_id, "failed", str(e))
            yield {"type": "error", "content": str(e)}

    async def run_sync(
        self,
        query: str,
        session_id: str,
        run_context: Dict[str, Any] = None,
        **_: Any,
    ) -> ResearchState:
        """
        同步执行（返回最终状态）

        用于不需要流式输出的场景
        """
        state = create_initial_state(query, session_id)
        if run_context:
            state["run_context"] = run_context
        state["max_iterations"] = self.max_iterations

        # 依次执行各阶段
        state = await self.architect.process(state)
        state["phase"] = ResearchPhase.RESEARCHING.value
        state = await self.scout.process(state)
        state["phase"] = ResearchPhase.ANALYZING.value
        state = await self.data_analyst.process(state)
        state["phase"] = ResearchPhase.ANALYZING.value
        state = await self.wizard.process(state)
        state["phase"] = ResearchPhase.WRITING.value
        state = await self.writer.process(state)

        # 审核修订循环（支持智能路由）
        while state["iteration"] < state["max_iterations"]:
            state = await self.critic.process(state)

            if state["phase"] == ResearchPhase.COMPLETED.value:
                break

            # 智能路由：需要补充搜索
            if state["phase"] == ResearchPhase.RE_RESEARCHING.value:
                state = await self.scout.process(state)
                state["phase"] = ResearchPhase.WRITING.value
                state = await self.writer.process(state)

            # 仅需要文字修订
            elif state["phase"] == ResearchPhase.REVISING.value:
                state = await self.writer.process(state)
            else:
                break

        state.setdefault("quality_gates", {})["freshness"] = self.freshness_evaluator.evaluate(state)
        return state


def create_research_graph(
    llm_api_key: str = None,
    llm_base_url: str = None,
    search_api_key: str = None,
    model: str = None,
    deepscout_api_key: str = None,
    deepscout_base_url: str = None
) -> DeepResearchGraph:
    """
    工厂函数：创建 DeepResearch 工作流图

    所有参数都是可选的，会从配置文件读取默认值

    Args:
        llm_api_key: LLM API 密钥（可选，默认从配置读取，5 个核心 Agent 使用）
        llm_base_url: LLM API 基础 URL（可选，默认从配置读取）
        search_api_key: 搜索 API 密钥（可选，默认从配置读取）
        model: 默认模型名称（可选，默认从配置读取）
        deepscout_api_key: DeepScout 独立 API 密钥（可选，默认从配置读取）
        deepscout_base_url: DeepScout 独立 Base URL（可选，默认从配置读取）

    Returns:
        DeepResearchGraph 实例
    """
    return DeepResearchGraph(
        llm_api_key=llm_api_key,
        llm_base_url=llm_base_url,
        search_api_key=search_api_key,
        model=model,
        deepscout_api_key=deepscout_api_key,
        deepscout_base_url=deepscout_base_url
    )
