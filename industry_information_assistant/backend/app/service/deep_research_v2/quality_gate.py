"""Deterministic report checks performed before semantic review."""

import re
from typing import Any, Dict, List
from urllib.parse import urlsplit


def _valid_url(value: str) -> bool:
    try:
        parsed = urlsplit(value or "")
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
    except ValueError:
        return False


class DeterministicQualityGate:
    @classmethod
    def evaluate(cls, state: Dict[str, Any]) -> Dict[str, Any]:
        report = state.get("final_report", "")
        outline = state.get("outline", [])
        facts = state.get("facts", [])
        charts = state.get("charts", [])
        issues: List[Dict[str, Any]] = []

        missing_sections = [s.get("title", s.get("id", "")) for s in outline if s.get("title", "").lower() not in report.lower()]
        if missing_sections:
            issues.append(cls._issue("incomplete", "major", f"缺少章节：{', '.join(missing_sections[:5])}"))
        if not report.strip():
            issues.append(cls._issue("incomplete", "critical", "报告正文为空"))

        sourced_facts = [fact for fact in facts if _valid_url(str(fact.get("source_url", "")))]
        if facts and len(sourced_facts) / len(facts) < 0.6:
            issues.append(cls._issue("missing_source", "major", "有效 URL 的事实占比低于 60%"))
        if len(sourced_facts) < min(3, len(outline)):
            issues.append(cls._issue("missing_source", "major", "有效来源数量未达到章节覆盖要求"))

        evidence_ids = {str(f.get("evidence_id") or f.get("id", "")) for f in facts}
        report_citations = set(re.findall(r"\[([^\]]+)\]", report))
        if facts and not (report_citations & evidence_ids):
            issues.append(cls._issue("missing_source", "major", "报告正文未引用任何已知 evidence_id"))
        unknown = {citation for citation in report_citations if citation.startswith(("ev_", "fact_")) and citation not in evidence_ids}
        if unknown:
            issues.append(cls._issue("missing_source", "major", f"存在未知证据引用：{', '.join(sorted(unknown)[:5])}"))

        data_ids = {str(item.get("id", "")) for item in state.get("data_points", [])}
        broken_charts = [chart.get("id", "") for chart in charts if chart.get("data_point_ids") and not set(chart["data_point_ids"]).issubset(data_ids)]
        if broken_charts:
            issues.append(cls._issue("logic_error", "major", "图表引用了不存在的数据点"))

        severe = [issue for issue in issues if issue["severity"] in {"critical", "major"}]
        needs_research = any(issue["issue_type"] in {"missing_source", "outdated"} for issue in severe)
        return {
            "passed": not severe,
            "verdict": "PASS" if not severe else ("RESEARCH" if needs_research else "REVISE"),
            "issues": issues,
            "source_count": len(sourced_facts),
            "section_count": len(outline),
        }

    @staticmethod
    def _issue(issue_type: str, severity: str, description: str) -> Dict[str, Any]:
        return {"issue_type": issue_type, "severity": severity, "description": description, "suggestion": "补齐后重新检查"}
