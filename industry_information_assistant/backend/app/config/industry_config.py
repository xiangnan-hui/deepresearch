
"""
行业配置 - 定义各行业的搜索关键词
"""
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class IndustryConfig:
    """行业配置"""
    id: str
    name: str
    description: str
    news_keywords: List[str]
    bidding_keywords: List[str]
    research_keywords: List[str]


# 预定义的行业配置
INDUSTRY_CONFIGS: Dict[str, IndustryConfig] = {
    "artificial_intelligence": IndustryConfig(
        id="artificial_intelligence",
        name="人工智能",
        description="大模型、生成式 AI、智能体、算力与 AI 应用创新",
        news_keywords=[
            "人工智能 最新进展",
            "大模型 发布",
            "生成式人工智能 政策",
            "AI Agent 智能体",
            "多模态模型",
            "推理模型",
            "AI 芯片 算力",
            "开源大模型",
            "人工智能 融合应用",
        ],
        bidding_keywords=[],
        research_keywords=[
            "人工智能",
            "大模型",
            "生成式 AI",
            "AI Agent",
            "多模态",
            "推理模型",
            "AI 芯片",
        ],
    ),
}

# 默认行业
DEFAULT_INDUSTRY_ID = "artificial_intelligence"


def get_industry_config(industry_id: Optional[str] = None) -> IndustryConfig:
    """
    获取行业配置

    Args:
        industry_id: 行业ID，如果为空则返回默认行业

    Returns:
        行业配置
    """
    if not industry_id:
        industry_id = DEFAULT_INDUSTRY_ID

    config = INDUSTRY_CONFIGS.get(industry_id)
    if not config:
        logger.warning(f"[industry_config] 未找到行业配置: {industry_id}, 使用默认行业")
        config = INDUSTRY_CONFIGS[DEFAULT_INDUSTRY_ID]

    logger.info(f"[industry_config] 获取行业配置: {config.name} ({config.id})")
    return config


def get_all_industries() -> List[Dict]:
    """
    获取所有行业列表

    Returns:
        行业列表
    """
    return [
        {
            "id": config.id,
            "name": config.name,
            "description": config.description,
            "news_keywords": config.news_keywords,
            "research_keywords": config.research_keywords,
        }
        for config in INDUSTRY_CONFIGS.values()
    ]
