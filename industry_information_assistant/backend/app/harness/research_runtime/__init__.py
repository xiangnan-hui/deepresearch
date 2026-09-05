"""Interactive Research 运行时。"""

from .models import CommandType, ResearchStatus


def get_research_runtime():
    """延迟加载依赖数据库/Redis 的运行时，保持纯模型模块可独立测试。"""
    from .coordinator import get_research_runtime as factory
    return factory()


__all__ = ["get_research_runtime", "CommandType", "ResearchStatus"]
