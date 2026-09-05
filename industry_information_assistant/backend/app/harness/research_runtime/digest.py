"""从结构化研究事件生成轻量摘要。"""

from typing import Any, Dict

from .models import ResearchDigest, utc_now


class ResearchDigestBuilder:
    def update(self, current: Dict[str, Any], event: Dict[str, Any]) -> Dict[str, Any]:
        digest = ResearchDigest(**{k: v for k, v in current.items() if k in ResearchDigest.__dataclass_fields__})
        event_type = event.get("type", "")
        content = event.get("content")
        if event_type == "phase":
            digest.current_focus = str(event.get("phase", ""))
            digest.summary = self._text(content) or f"正在进行 {digest.current_focus} 阶段。"
        elif event_type in {"thought", "observation", "review"}:
            text = self._text(content)
            if text:
                digest.summary = text[:500]
        elif event_type == "outline" and isinstance(content, dict):
            digest.open_questions = list(content.get("research_questions", []))[:10]
        elif event_type == "research_complete":
            digest.summary = "研究已完成，最终报告已经生成。"
            digest.current_focus = "completed"
            digest.next_steps = []
        digest.updated_at = utc_now()
        return digest.to_dict()

    @staticmethod
    def _text(content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, dict):
            return str(content.get("content") or content.get("summary") or "")
        return ""
