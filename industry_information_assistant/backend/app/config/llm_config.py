
"""
LLM 和 Agent 配置文件

集中管理所有 LLM 相关配置，所有值均来自统一配置模块 config.settings（环境变量），
包括：
- DeepSeek V4 配置（5 个核心 Agent 共用的 API Key、Base URL）
- DeepScout 独立配置（API Key、Base URL、模型 glm-5.2）
- DashScope 配置（Embedding / Rerank / 长期记忆 / V1 流程）
- 每个 Agent 节点的模型配置
- 研究流程参数

Agent 模型映射（可通过 .env 覆盖）：
    ChiefArchitect -> DEEPSEEK V4 (CHIEF_ARCHITECT_MODEL)
    DataAnalyst    -> DEEPSEEK V4 (DATA_ANALYST_MODEL)
    CodeWizard     -> DEEPSEEK V4 (CODE_WIZARD_MODEL)
    LeadWriter     -> DEEPSEEK V4 (LEAD_WRITER_MODEL)
    CriticMaster   -> DEEPSEEK V4 (CRITIC_MASTER_MODEL)
    DeepScout      -> glm-5.2 (DEEPSCOUT_MODEL)

使用方式:
    from app.config.llm_config import LLMConfig, AgentConfig

    config = LLMConfig()
    print(config.default_model)
    print(config.agents.wizard.model)
"""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any

from config.settings import settings


@dataclass
class AgentModelConfig:
    """单个 Agent 的模型配置"""
    model: str
    temperature: float = 0.7
    max_tokens: int = 8000

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens
        }


@dataclass
class AgentsConfig:
    """所有 Agent 的配置（模型名来自环境变量，默认符合项目 Agent 架构要求）"""
    # 总架构师 - 分析问题，生成研究大纲（DeepSeek V4）
    architect: AgentModelConfig = field(default_factory=lambda: AgentModelConfig(
        model=settings.chief_architect_model,
        temperature=0.7,
        max_tokens=4000
    ))

    # 深度侦探 - 深度搜索（glm-5.2，独立 Key/Base URL）
    scout: AgentModelConfig = field(default_factory=lambda: AgentModelConfig(
        model=settings.deepscout_model,
        temperature=0.5,
        max_tokens=4000
    ))

    # 数据分析师 - 数据提取和分析（DeepSeek V4）
    data_analyst: AgentModelConfig = field(default_factory=lambda: AgentModelConfig(
        model=settings.data_analyst_model,
        temperature=0.3,
        max_tokens=8000
    ))

    # 代码极客 - 代码生成和图表绘制（DeepSeek V4）
    wizard: AgentModelConfig = field(default_factory=lambda: AgentModelConfig(
        model=settings.code_wizard_model,
        temperature=0.3,
        max_tokens=8000
    ))

    # 审核大师 - 对抗式审核（DeepSeek V4）
    critic: AgentModelConfig = field(default_factory=lambda: AgentModelConfig(
        model=settings.critic_master_model,
        temperature=0.5,
        max_tokens=4000
    ))

    # 首席笔杆 - 报告撰写（DeepSeek V4）
    writer: AgentModelConfig = field(default_factory=lambda: AgentModelConfig(
        model=settings.lead_writer_model,
        temperature=0.7,
        max_tokens=16000
    ))


@dataclass
class ResearchConfig:
    """研究流程配置（均支持环境变量覆盖）"""
    # 最大迭代次数（审核-修订循环）
    max_iterations: int = settings.research_max_iterations

    # 每个章节最大搜索数量
    max_searches_per_section: int = settings.research_max_searches_per_section

    # 最大图表数量
    max_charts: int = settings.research_max_charts

    # 是否启用代码执行
    enable_code_execution: bool = settings.research_enable_code_execution

    # 质量评分阈值（1-10分制，低于此分数需要修订）
    quality_threshold: float = settings.research_quality_threshold


@dataclass
class LLMConfig:
    """
    LLM 配置主类

    集中管理所有配置，全部从统一配置模块 config.settings 读取（环境变量）。
    """

    # ==================== DeepSeek V4（5 个核心 Agent） ====================
    api_key: str = field(default_factory=lambda: settings.deepseek_api_key)
    base_url: str = field(default_factory=lambda: settings.deepseek_base_url)

    # ==================== DeepScout（独立配置） ====================
    deepscout_api_key: str = field(default_factory=lambda: settings.deepscout_api_key)
    deepscout_base_url: str = field(default_factory=lambda: settings.deepscout_base_url)

    # ==================== DashScope（Embedding / 长期记忆 / V1 流程） ====================
    dashscope_api_key: str = field(default_factory=lambda: settings.dashscope_api_key)
    dashscope_base_url: str = field(default_factory=lambda: settings.dashscope_base_url)
    dashscope_model: str = field(default_factory=lambda: settings.dashscope_model)

    # 搜索 API（博查）
    search_api_key: str = field(default_factory=lambda: settings.bocha_api_key)

    # 默认模型（用于未单独配置的场景）
    default_model: str = field(default_factory=lambda: settings.deepseek_default_model)

    # Agent 配置
    agents: AgentsConfig = field(default_factory=AgentsConfig)

    # 研究流程配置
    research: ResearchConfig = field(default_factory=ResearchConfig)

    def get_agent_config(self, agent_name: str) -> AgentModelConfig:
        """获取指定 Agent 的配置"""
        agent_configs = {
            "architect": self.agents.architect,
            "scout": self.agents.scout,
            "data_analyst": self.agents.data_analyst,
            "wizard": self.agents.wizard,
            "critic": self.agents.critic,
            "writer": self.agents.writer,
        }
        return agent_configs.get(agent_name, AgentModelConfig(model=self.default_model))

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式（密钥脱敏）"""
        return {
            "deepseek": {
                "api_key": self._mask(self.api_key),
                "base_url": self.base_url,
                "default_model": self.default_model,
            },
            "deepscout": {
                "api_key": self._mask(self.deepscout_api_key),
                "base_url": self.deepscout_base_url,
            },
            "dashscope": {
                "api_key": self._mask(self.dashscope_api_key),
                "base_url": self.dashscope_base_url,
                "model": self.dashscope_model,
            },
            "search_api_key": self._mask(self.search_api_key),
            "agents": {
                "architect": self.agents.architect.to_dict(),
                "scout": self.agents.scout.to_dict(),
                "data_analyst": self.agents.data_analyst.to_dict(),
                "wizard": self.agents.wizard.to_dict(),
                "critic": self.agents.critic.to_dict(),
                "writer": self.agents.writer.to_dict(),
            },
            "research": {
                "max_iterations": self.research.max_iterations,
                "max_searches_per_section": self.research.max_searches_per_section,
                "max_charts": self.research.max_charts,
                "enable_code_execution": self.research.enable_code_execution,
                "quality_threshold": self.research.quality_threshold,
            }
        }

    @staticmethod
    def _mask(key: str) -> str:
        """密钥脱敏显示"""
        if not key:
            return ""
        return key[:8] + "..." if len(key) > 8 else "***"


# 全局配置实例（单例模式）
_config_instance: Optional[LLMConfig] = None


def get_config() -> LLMConfig:
    """获取全局配置实例"""
    global _config_instance
    if _config_instance is None:
        _config_instance = LLMConfig()
    return _config_instance


def reload_config() -> LLMConfig:
    """重新加载配置"""
    global _config_instance
    _config_instance = LLMConfig()
    return _config_instance


# 便捷访问
def get_agent_model(agent_name: str) -> str:
    """快速获取指定 Agent 的模型名称"""
    return get_config().get_agent_config(agent_name).model


def get_default_model() -> str:
    """快速获取默认模型"""
    return get_config().default_model


# 用于打印配置信息
def print_config():
    """打印当前配置（用于调试）"""
    import json
    config = get_config()
    print("=" * 60)
    print("LLM Configuration")
    print("=" * 60)
    print(json.dumps(config.to_dict(), indent=2, ensure_ascii=False))
    print("=" * 60)


if __name__ == "__main__":
    # 测试配置
    print_config()
