"""Deterministic ECharts builder for common research data shapes."""

import uuid
import re
from typing import Any, Dict, List


class ChartBuilder:
    COLORS = ["#1677ff", "#52c41a", "#722ed1", "#fa8c16", "#eb2f96"]

    @classmethod
    def build(cls, extracted: Dict[str, Any], evidence: List[Dict[str, Any]] = None, limit: int = 3) -> List[Dict[str, Any]]:
        charts: List[Dict[str, Any]] = []
        for series in extracted.get("time_series", []):
            rows = series.get("data") or []
            if len(rows) < 2:
                continue
            charts.append(cls._axis_chart(series.get("metric", "趋势"), rows, "line", series.get("unit", "")))
            if len(charts) >= limit:
                return charts
        for distribution in extracted.get("distributions", []):
            rows = distribution.get("data") or []
            if len(rows) < 2:
                continue
            charts.append(cls._pie_chart(distribution.get("name", "分布"), rows))
            if len(charts) >= limit:
                return charts
        points = cls._normalize_points(extracted.get("data_points", []))
        if not points:
            points = cls.extract_points(evidence or [])
            extracted["data_points"] = points
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for row in points:
            grouped.setdefault(str(row.get("unit", "")), []).append(row)
        for unit, rows in sorted(grouped.items(), key=lambda item: len(item[1]), reverse=True):
            if len(rows) >= 2 and len(charts) < limit:
                charts.append(cls._axis_chart(f"关键指标对比（{unit or '数值'}）", rows[:10], "bar", unit))
        return charts

    @staticmethod
    def _normalize_points(points: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = []
        for point in points:
            value = point.get("value")
            if isinstance(value, str):
                match = re.search(r"-?\d+(?:\.\d+)?", value.replace(",", ""))
                value = float(match.group()) if match else None
            if isinstance(value, (int, float)):
                normalized.append({**point, "value": value})
        return normalized

    @classmethod
    def extract_points(cls, evidence: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Conservative fallback: extract explicit percentages from sourced evidence."""
        points = []
        seen = set()
        for fact in evidence:
            content = str(fact.get("content", ""))
            for match in re.finditer(r"(\d+(?:\.\d+)?)\s*(%|％)", content):
                label = re.sub(r"\s+", "", content[max(0, match.start() - 24):match.end() + 10])
                key = (label, match.group(1))
                if key in seen:
                    continue
                seen.add(key)
                points.append({
                    "id": f"dp_{uuid.uuid4().hex[:8]}", "name": label[:40],
                    "value": float(match.group(1)), "unit": "%", "year": None,
                    "source": fact.get("evidence_id") or fact.get("id", ""), "confidence": fact.get("credibility_score", 0.5),
                })
        return points[:12]

    @classmethod
    def _axis_chart(cls, title: str, rows: List[Dict[str, Any]], chart_type: str, unit: str) -> Dict[str, Any]:
        labels = [str(row.get("year") or row.get("name") or row.get("category") or "") for row in rows]
        values = [row.get("value", 0) for row in rows]
        return {
            "id": f"chart_{uuid.uuid4().hex[:8]}", "title": title, "subtitle": unit,
            "type": chart_type,
            "echarts_option": {
                "grid": {"left": "3%", "right": "4%", "bottom": "3%", "containLabel": True},
                "xAxis": {"type": "category", "data": labels},
                "yAxis": {"type": "value", "name": unit},
                "series": [{"type": chart_type, "data": values, "itemStyle": {"color": cls.COLORS[0]}, "smooth": chart_type == "line"}],
            },
        }

    @classmethod
    def _pie_chart(cls, title: str, rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        data = [{"name": str(row.get("category") or row.get("name") or ""), "value": row.get("value", 0)} for row in rows]
        return {
            "id": f"chart_{uuid.uuid4().hex[:8]}", "title": title, "subtitle": "", "type": "pie",
            "echarts_option": {"color": cls.COLORS, "tooltip": {"trigger": "item"}, "series": [{"type": "pie", "radius": ["35%", "65%"], "data": data}]},
        }


def build_knowledge_graph(extracted: Dict[str, Any], evidence: List[Dict[str, Any]] = None, query: str = "") -> Dict[str, Any]:
    nodes = []
    known = set()
    for entity in extracted.get("entities", []):
        node_id = str(entity.get("id") or entity.get("name") or "").strip()
        if not node_id or node_id in known:
            continue
        known.add(node_id)
        importance = max(1, min(10, int(entity.get("importance", 5) or 5)))
        nodes.append({**entity, "id": node_id, "size": 20 + importance * 3})
    edges = [edge for edge in extracted.get("relations", []) if edge.get("source") in known and edge.get("target") in known]
    if not nodes and evidence:
        core_id = "research_topic"
        nodes.append({"id": core_id, "name": query[:30] or "研究主题", "type": "core", "importance": 10, "size": 50})
        known.add(core_id)
        entity_pattern = re.compile(r"OpenAI|Anthropic|Google|DeepSeek|NVIDIA|Microsoft|Meta|Gartner|IDC|LangGraph|AI Agent", re.I)
        names = []
        for fact in evidence:
            names.extend(entity_pattern.findall(str(fact.get("content", ""))))
        for name in list(dict.fromkeys(names))[:12]:
            node_id = re.sub(r"\W+", "_", name.lower()).strip("_")
            if not node_id or node_id in known:
                continue
            known.add(node_id)
            nodes.append({"id": node_id, "name": name, "type": "company" if name.lower() not in {"langgraph", "ai agent"} else "tech", "importance": 6, "size": 38})
            edges.append({"source": node_id, "target": core_id, "relation": "相关"})
    elif len(nodes) > 1 and not edges:
        core = next((node for node in nodes if node.get("type") == "core"), None)
        if core is None:
            core = {"id": "research_topic", "name": query[:30] or "研究主题", "type": "core", "importance": 10, "size": 50}
            nodes.insert(0, core)
        edges.extend(
            {"source": node["id"], "target": core["id"], "relation": "相关"}
            for node in nodes if node["id"] != core["id"]
        )
    return {"nodes": nodes, "edges": edges}
