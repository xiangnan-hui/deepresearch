"""
统一配置模块 - 全项目唯一的环境变量入口

所有环境相关配置（API Key、模型名称、服务地址、数据库连接、端口、超时、并发等）
都在此模块中集中读取和校验，业务代码一律通过 `settings` 单例获取配置，
禁止在业务代码中直接散落 os.getenv()。

使用方式:
    from config.settings import settings, validate_settings

    api_key = settings.deepseek_api_key
    validate_settings()  # 启动时校验必填配置，缺失时抛出带指引的 RuntimeError

兼容性说明:
    - 保留项目已有的全部环境变量名称（DASHSCOPE_API_KEY / BOCHA_API_KEY / POSTGRES_* 等），
      已有 .env 无需改名即可继续使用。
    - 新增 DeepSeek / DeepScout 系列变量，旧变量在新语义下仍被兼容读取
      （如 LLM_BASE_URL 仍作为 DASHSCOPE_BASE_URL 的备选）。
"""

import os
from typing import Optional, List

# 加载 .env 文件（默认从工作目录向上查找 backend/.env）
# python-dotenv 为可选依赖：未安装时仅使用系统环境变量（requirements.txt 中已声明）
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ---------------------------------------------------------------------------
# 类型转换辅助函数
# ---------------------------------------------------------------------------

def _get_str(*names: str, default: str = "") -> str:
    """按顺序读取第一个存在的环境变量，返回字符串"""
    for name in names:
        value = os.getenv(name)
        if value is not None and value != "":
            return value
    return default


def _get_int(*names: str, default: int) -> int:
    """按顺序读取第一个存在的环境变量，转换为 int（解析失败时回退默认值）"""
    raw = _get_str(*names, default="")
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_float(*names: str, default: float) -> float:
    """按顺序读取第一个存在的环境变量，转换为 float（解析失败时回退默认值）"""
    raw = _get_str(*names, default="")
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _get_bool(*names: str, default: bool) -> bool:
    """按顺序读取第一个存在的环境变量，转换为 bool"""
    raw = _get_str(*names, default="").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Settings 单例
# ---------------------------------------------------------------------------

class Settings:
    """全项目统一配置对象（单例，import 时完成读取）"""

    def __init__(self):
        # ==================== LLM - DashScope（Embedding / Rerank / 记忆 / V1 流程） ====================
        # 阿里云百炼 API（必填），用于 text-embedding-v4、Rerank、长期记忆等
        self.dashscope_api_key: str = _get_str("DASHSCOPE_API_KEY")
        # 兼容旧变量 LLM_BASE_URL
        self.dashscope_base_url: str = _get_str(
            "DASHSCOPE_BASE_URL", "LLM_BASE_URL",
            default="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        # DashScope 默认对话模型（长期记忆 / V1 研究流程 / 通用聊天）
        self.dashscope_model: str = _get_str("DASHSCOPE_MODEL", default="qwen3.7-plus")
        # 聊天服务模型（兼容旧变量 OPENAI_MODEL）
        self.chat_model: str = _get_str("OPENAI_MODEL", "DASHSCOPE_MODEL", default="qwen3.7-plus")
        # 聊天服务 Base URL（兼容旧变量 OPENAI_BASE_URL）
        self.chat_base_url: str = _get_str(
            "OPENAI_BASE_URL", "DASHSCOPE_BASE_URL",
            default="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        # V1 研究流程最终综合报告使用的模型
        self.research_synthesis_model: str = _get_str("RESEARCH_SYNTHESIS_MODEL", default="deepseek-r1")
        # OpenRouter（可选，保留旧变量兼容）
        self.openrouter_api_key: str = _get_str("OPENROUTER_API_KEY")

        # ==================== LLM - DeepSeek V4（5 个核心 Agent 共用） ====================
        # 5 个 Agent（ChiefArchitect/DataAnalyst/CodeWizard/LeadWriter/CriticMaster）共用
        # 同一 DeepSeek API Key 与 Base URL；如需为单个 Agent 使用不同 Key，
        # 可在调用层传入覆盖参数（graph/service 构造函数均支持）。
        self.deepseek_api_key: str = _get_str("DEEPSEEK_API_KEY")
        self.deepseek_base_url: str = _get_str("DEEPSEEK_BASE_URL", default="https://api.deepseek.com")
        self.deepseek_default_model: str = _get_str("DEEPSEEK_DEFAULT_MODEL", default="deepseek-v4")
        # 各 Agent 模型名（默认均为 deepseek-v4）
        self.chief_architect_model: str = _get_str("CHIEF_ARCHITECT_MODEL", default="deepseek-v4")
        self.data_analyst_model: str = _get_str("DATA_ANALYST_MODEL", default="deepseek-v4")
        self.code_wizard_model: str = _get_str("CODE_WIZARD_MODEL", default="deepseek-v4")
        self.lead_writer_model: str = _get_str("LEAD_WRITER_MODEL", default="deepseek-v4")
        self.critic_master_model: str = _get_str("CRITIC_MASTER_MODEL", default="deepseek-v4")

        # ==================== LLM - DeepScout（深度侦探，独立配置） ====================
        # DeepScout 使用 qwen3.7-plus-2026-05-26；
        # 未单独配置 DEEPSCOUT_API_KEY / DEEPSCOUT_BASE_URL 时回退到 DashScope 配置。
        self.deepscout_api_key: str = _get_str("DEEPSCOUT_API_KEY", "DASHSCOPE_API_KEY")
        self.deepscout_base_url: str = _get_str(
            "DEEPSCOUT_BASE_URL", "DASHSCOPE_BASE_URL",
            default="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )
        self.deepscout_model: str = _get_str("DEEPSCOUT_MODEL", default="qwen3.7-plus-2026-05-26")

        # ==================== Embedding / Rerank ====================
        self.embedding_model: str = _get_str("EMBEDDING_MODEL", default="text-embedding-v4")
        self.embedding_dimensions: int = _get_int("EMBEDDING_DIMENSIONS", default=1024)
        self.embedding_max_batch_size: int = _get_int("EMBEDDING_MAX_BATCH_SIZE", default=10)

        # ==================== 搜索服务 ====================
        # 博查搜索（必填）
        self.bocha_api_key: str = _get_str("BOCHA_API_KEY")
        self.bocha_base_url: str = _get_str(
            "BOCHA_BASE_URL", default="https://api.bochaai.com/v1/web-search"
        )
        self.bocha_request_timeout: float = _get_float("BOCHA_REQUEST_TIMEOUT", default=30.0)
        # Serper 搜索（可选）
        self.serper_api_key: str = _get_str("SERPER_API_KEY")
        self.serper_host: str = _get_str("SERPER_HOST", default="google.serper.dev")

        # ==================== PostgreSQL ====================
        self.database_url: str = _get_str("DATABASE_URL")
        self.postgres_host: str = _get_str("POSTGRES_HOST", default="localhost")
        self.postgres_port: int = _get_int("POSTGRES_PORT", default=5432)
        self.postgres_user: str = _get_str("POSTGRES_USER", default="postgres")
        # 开发环境默认密码与 docker-compose.yml 保持一致，生产环境务必修改
        self.postgres_password: str = _get_str("POSTGRES_PASSWORD", default="")
        self.postgres_db: str = _get_str("POSTGRES_DB", default="industry_assistant")

        # Redis
        self.redis_host: str = _get_str("REDIS_HOST", default="localhost")
        self.redis_port: int = _get_int("REDIS_PORT", default=6379)
        self.redis_password: Optional[str] = _get_str("REDIS_PASSWORD") or None
        self.redis_max_connections: int = _get_int("REDIS_MAX_CONNECTIONS", default=20)

        # Milvus
        self.milvus_host: str = _get_str("MILVUS_HOST", default="localhost")
        self.milvus_port: int = _get_int("MILVUS_PORT", default=19530)
        self.policy_collection: str = _get_str("POLICY_COLLECTION", default="policy_documents")

        # ==================== RAGFlow 文档 API ====================
        self.ragflow_base_url: str = _get_str("API_BASE_URL", default="http://localhost:9380")
        self.ragflow_api_key: str = _get_str("API_KEY")
        self.ragflow_default_dataset_id: str = _get_str("DEFAULT_DATASET_ID")

        # ==================== DocMind 文档解析 ====================
        self.docmind_access_key_id: str = _get_str("DOCMIND_ACCESS_KEY_ID")
        self.docmind_access_key_secret: str = _get_str("DOCMIND_ACCESS_KEY_SECRET")
        self.docmind_endpoint: str = _get_str(
            "DOCMIND_ENDPOINT", default="docmind-api.cn-hangzhou.aliyuncs.com"
        )
        self.docmind_poll_interval: int = _get_int("DOCMIND_POLL_INTERVAL", default=5)
        self.docmind_max_wait: int = _get_int("DOCMIND_MAX_WAIT", default=300)

        # ==================== 股票行情（聚合数据） ====================
        self.juhe_stock_api_key: str = _get_str("JUHE_STOCK_API_KEY")
        self.juhe_stock_base_url: str = _get_str(
            "JUHE_STOCK_BASE_URL", default="http://web.juhe.cn/finance/stock/hs"
        )
        self.juhe_stock_shall_url: str = _get_str(
            "JUHE_STOCK_SHALL_URL", default="http://web.juhe.cn/finance/stock/shall"
        )
        self.juhe_stock_szall_url: str = _get_str(
            "JUHE_STOCK_SZALL_URL", default="http://web.juhe.cn/finance/stock/szall"
        )
        self.juhe_stock_timeout: float = _get_float("JUHE_STOCK_TIMEOUT", default=10.0)

        # ==================== 招投标（81API） ====================
        self.bid_app_key: str = _get_str("BID_APP_KEY")
        self.bid_app_secret: str = _get_str("BID_APP_SECRET")
        self.bid_app_code: str = _get_str("BID_APP_CODE")
        self.bid_base_url: str = _get_str("BID_API_BASE_URL", default="https://bid.81api.com")
        self.bid_request_timeout: float = _get_float("BID_REQUEST_TIMEOUT", default=15.0)

        # ==================== JWT 认证 ====================
        self.jwt_secret_key: str = _get_str(
            "JWT_SECRET_KEY", default=""
        )
        self.jwt_algorithm: str = _get_str("JWT_ALGORITHM", default="HS256")
        self.jwt_access_token_expire_minutes: int = _get_int(
            "JWT_ACCESS_TOKEN_EXPIRE_MINUTES", default=1440
        )

        # ==================== 深度研究流程参数 ====================
        self.research_max_iterations: int = _get_int("RESEARCH_MAX_ITERATIONS", default=1)
        self.research_max_searches_per_section: int = _get_int(
            "RESEARCH_MAX_SEARCHES_PER_SECTION", default=3
        )
        self.research_max_charts: int = _get_int("RESEARCH_MAX_CHARTS", default=5)
        self.research_quality_threshold: float = _get_float(
            "RESEARCH_QUALITY_THRESHOLD", default=6.0
        )
        self.research_enable_code_execution: bool = _get_bool(
            "RESEARCH_ENABLE_CODE_EXECUTION", default=True
        )
        # V1（ReAct）流程参数
        self.research_max_concurrent_searches: int = _get_int(
            "RESEARCH_MAX_CONCURRENT_SEARCHES", default=3
        )
        self.research_search_cache_ttl: int = _get_int("RESEARCH_SEARCH_CACHE_TTL", default=3600)
        self.research_content_similarity_threshold: float = _get_float(
            "RESEARCH_CONTENT_SIMILARITY_THRESHOLD", default=0.8
        )
        self.react_max_steps: int = _get_int("REACT_MAX_STEPS", default=10)

        # ==================== 长期记忆 ====================
        self.memory_token_threshold: int = _get_int("MEMORY_TOKEN_THRESHOLD", default=10000)
        self.memory_collection_name: str = _get_str(
            "MEMORY_COLLECTION_NAME", default="long_term_memories"
        )

        # ==================== 聊天 / 会话 ====================
        self.chat_max_tokens: int = _get_int("CHAT_MAX_TOKENS", default=12000)
        self.session_token_limit: int = _get_int("SESSION_TOKEN_LIMIT", default=5000)
        self.session_max_messages: int = _get_int("SESSION_MAX_MESSAGES", default=20)

        # ==================== Text2SQL ====================
        self.text2sql_model: str = _get_str("TEXT2SQL_MODEL", default="qwen3.7-plus")

        # ==================== 应用服务 ====================
        self.app_host: str = _get_str("APP_HOST", default="0.0.0.0")
        self.app_port: int = _get_int("APP_PORT", default=8000)
        self.cors_origins: List[str] = [
            origin.strip()
            for origin in _get_str("CORS_ORIGINS", default="*").split(",")
            if origin.strip()
        ]
        self.timezone: str = _get_str("TIMEZONE", default="Asia/Shanghai")
        self.mem_limit: str = _get_str("MEM_LIMIT", default="")

    # -----------------------------------------------------------------------
    # 派生配置（URL 拼接等统一在此处理）
    # -----------------------------------------------------------------------

    @property
    def sqlalchemy_database_url(self) -> str:
        """PostgreSQL 连接串：优先 DATABASE_URL，否则由 POSTGRES_* 拼接"""
        if self.database_url:
            return self.database_url
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def validate(self) -> List[str]:
        """
        启动时校验必填配置

        Returns:
            警告信息列表（非致命）；缺失必填项时抛出 RuntimeError，
            错误信息中给出明确的修复指引。
        """
        missing: List[str] = []

        if not self.dashscope_api_key:
            missing.append("DASHSCOPE_API_KEY（阿里云百炼 API Key，Embedding/Rerank/长期记忆/V1 流程必需）")
        if not self.bocha_api_key:
            missing.append("BOCHA_API_KEY（博查搜索 API Key，网络搜索必需）")
        if not self.deepseek_api_key:
            missing.append("DEEPSEEK_API_KEY（DeepSeek API Key，5 个核心 Agent 必需）")
        if not self.deepscout_api_key:
            missing.append("DEEPSCOUT_API_KEY（DeepScout API Key；或设置 DASHSCOPE_API_KEY 作为回退）")

        if missing:
            raise RuntimeError(
                "配置校验失败，以下必填环境变量未设置（请在 backend/.env 中填写）：\n"
                + "\n".join(f"  - {item}" for item in missing)
                + "\n\n可参考 backend/.env.example 完成配置。"
            )

        warnings: List[str] = []
        if not self.jwt_secret_key:
            warnings.append(
                "JWT_SECRET_KEY 仍为默认占位值，生产环境请务必更换为随机密钥"
            )
        if not self.postgres_password:
            warnings.append(
                "POSTGRES_PASSWORD 仍为开发默认密码，生产环境请务必修改"
            )
        if not self.ragflow_api_key:
            warnings.append(
                "API_KEY（RAGFlow 文档服务）未设置，文档上传/检索功能将不可用"
            )
        return warnings


# 单例实例
settings = Settings()


def validate_settings() -> None:
    """启动时校验配置（打印警告、缺失必填项时抛异常）"""
    import logging
    logger = logging.getLogger(__name__)
    for warning in settings.validate():
        logger.warning(f"[配置] {warning}")
    logger.info("配置校验通过")
