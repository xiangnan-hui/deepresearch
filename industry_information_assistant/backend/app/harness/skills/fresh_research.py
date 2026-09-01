"""Reusable temporal grounding skill for time-sensitive research."""

from datetime import datetime
from typing import Any, Dict


class FreshResearchSkill:
    name = "fresh_research"

    @staticmethod
    def instruction(run_context: Dict[str, Any]) -> str:
        policy = run_context.get("freshness", {})
        if not policy.get("required"):
            return ""
        return (
            f"当前时间：{run_context.get('current_time', '')}"
            f"（{run_context.get('timezone', '')}）。用户要求最新信息。"
            f"搜索词必须覆盖当前年份和最近 {policy.get('window_days', 365)} 天，"
            "优先官方发布、论文、技术文档和项目 release notes；旧资料仅可作为历史背景。"
        )

    @staticmethod
    def decorate_query(query: str, run_context: Dict[str, Any]) -> str:
        policy = run_context.get("freshness", {})
        if not policy.get("required"):
            return query
        current_time = str(run_context.get("current_time", ""))
        try:
            current_year = datetime.fromisoformat(current_time).year
        except ValueError:
            current_year = datetime.now().year
        if str(current_year) in query:
            return query
        return f"{query} {current_year} 最新 官方"
