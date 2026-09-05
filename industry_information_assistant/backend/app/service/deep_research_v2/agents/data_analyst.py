

"""
DeepResearch V2.0 - 数据分析师 Agent (DataAnalyst)

职责：
1. 从搜索结果中提取结构化数据
2. 构建知识图谱(实体+关系)
3. 生成可视化图表配置(ECharts)
4. 识别数据趋势和洞察
"""

import uuid
from typing import Dict, Any, List
from datetime import datetime

from .base import BaseAgent
from ..state import ResearchState, ResearchPhase
from ..chart_builder import ChartBuilder, build_knowledge_graph


class DataAnalyst(BaseAgent):
    """
    数据分析师 - 专注于数据提取、知识图谱和可视化

    特点：
    - 从文本中提取结构化数据点
    - 构建实体关系知识图谱
    - 生成ECharts可视化配置
    - 识别趋势和洞察
    """

    COMBINED_EXTRACTION_PROMPT = """从证据中一次性提取可验证的数据与实体关系。

研究主题：{query}
证据（保留 evidence_id 与来源）：
{search_results}

只输出最小 JSON：
{{
  "data_points": [{{"id":"dp_1","name":"指标","value":1,"unit":"","year":2026,"source":"ev_x","confidence":0.8}}],
  "time_series": [{{"metric":"指标","unit":"","data":[{{"year":2025,"value":1}}],"source":"ev_x"}}],
  "distributions": [{{"name":"分布","data":[{{"category":"A","value":1,"unit":"%"}}],"source":"ev_x"}}],
  "facts": [{{"content":"事实","source":"ev_x"}}],
  "entities": [{{"id":"entity_id","name":"实体","type":"company","importance":5}}],
  "relations": [{{"source":"entity_id","target":"other_id","relation":"关联"}}],
  "insights": ["简短洞察"]
}}
没有对应内容时返回空数组；不得补造证据中不存在的数据。"""

    # 数据提取 Prompt
    DATA_EXTRACTION_PROMPT = """你是专业的数据分析师，擅长从文本中提取结构化数据。

## 研究主题
{query}

## 搜索结果
{search_results}

## 任务
从以上搜索结果中提取所有可量化的数据点，包括：
1. 市场规模数据（金额、单位、年份）
2. 增长率数据（百分比、时间段）
3. 市场份额数据（企业/领域、占比）
4. 排名数据（企业、产品、技术）
5. 时间序列数据（同一指标在不同年份的值）

## 输出要求
请输出JSON格式：
```json
{{
    "data_points": [
        {{
            "id": "dp_001",
            "name": "中国AI市场规模",
            "value": 5000,
            "unit": "亿元",
            "year": 2024,
            "source": "艾瑞咨询",
            "category": "market_size",
            "confidence": 0.9
        }}
    ],
    "time_series": [
        {{
            "id": "ts_001",
            "metric": "AI市场规模",
            "unit": "亿元",
            "data": [
                {{"year": 2020, "value": 3200}},
                {{"year": 2021, "value": 4100}},
                {{"year": 2024, "value": 8500}}
            ],
            "source": "艾瑞咨询"
        }}
    ],
    "distributions": [
        {{
            "id": "dist_001",
            "name": "细分领域市场份额",
            "year": 2024,
            "data": [
                {{"category": "计算机视觉", "value": 32, "unit": "%"}},
                {{"category": "自然语言处理", "value": 28, "unit": "%"}}
            ],
            "source": "IDC"
        }}
    ],
    "insights": [
        "中国AI市场规模在2024年突破5000亿元",
        "计算机视觉是最大的细分领域，占比32%"
    ]
}}
```

注意：
- 只提取有明确来源的数据
- confidence表示数据可信度(0-1)
- 如果没有找到相关数据，返回空数组"""

    # 知识图谱构建 Prompt
    KNOWLEDGE_GRAPH_PROMPT = """你是知识图谱专家，擅长从文本中提取实体和关系。

## 研究主题
{query}

## 文本内容
{content}

## 任务
从以上文本中提取实体和关系，构建知识图谱。

## 实体类型定义
- core: 核心概念（如：人工智能、大模型）
- tech: 技术（如：深度学习、计算机视觉、NLP）
- company: 企业（如：百度、阿里巴巴、华为）
- policy: 政策（如：AI发展规划、数据安全法）
- product: 产品（如：ChatGPT、文心一言）
- person: 人物（如：创始人、CEO）

## 输出要求
请输出JSON格式：
```json
{{
    "nodes": [
        {{"id": "ai", "name": "人工智能", "type": "core", "importance": 10}},
        {{"id": "baidu", "name": "百度", "type": "company", "importance": 8}},
        {{"id": "cv", "name": "计算机视觉", "type": "tech", "importance": 7}}
    ],
    "edges": [
        {{"source": "baidu", "target": "ai", "relation": "布局"}},
        {{"source": "cv", "target": "ai", "relation": "属于"}},
        {{"source": "baidu", "target": "cv", "relation": "研发"}}
    ]
}}
```

注意：
- importance范围1-10，表示节点重要性
- 核心概念(core)的importance最高
- 提取5-15个最重要的实体
- 关系要简洁，2-4个字"""

    # 图表生成 Prompt
    CHART_GENERATION_PROMPT = """你是数据可视化专家，擅长生成ECharts图表配置。

## 研究主题
{query}

## 可用数据
{data}

## 任务
根据数据生成合适的ECharts图表配置，选择最能展示数据特点的图表类型。

## 图表类型选择规则
- 时间序列数据 → line (折线图)
- 分类比较数据 → bar (柱状图)
- 占比分布数据 → pie (饼图)
- 进度/百分比 → horizontal_bar (横向进度条)
- 多维对比 → radar (雷达图)

## 设计要求
1. 配色使用简约专业色系：
   - 主色：#1677ff (蓝)
   - 辅助色：#52c41a (绿), #722ed1 (紫), #fa8c16 (橙), #eb2f96 (粉)
2. 标题简洁明了
3. 不要过多装饰，保持简约

## 输出要求
请输出JSON格式：
```json
{{
    "charts": [
        {{
            "id": "chart_001",
            "title": "中国AI市场规模",
            "subtitle": "2020-2024年市场规模（亿元）",
            "type": "line",
            "echarts_option": {{
                "grid": {{"left": "3%", "right": "4%", "bottom": "3%", "containLabel": true}},
                "xAxis": {{
                    "type": "category",
                    "data": ["2020", "2021", "2022", "2023", "2024"],
                    "axisLine": {{"lineStyle": {{"color": "#e8e8e8"}}}},
                    "axisLabel": {{"color": "#666"}}
                }},
                "yAxis": {{
                    "type": "value",
                    "axisLine": {{"show": false}},
                    "splitLine": {{"lineStyle": {{"color": "#f0f0f0"}}}}
                }},
                "series": [{{
                    "type": "line",
                    "data": [3200, 4100, 5200, 6800, 8500],
                    "smooth": true,
                    "symbol": "circle",
                    "symbolSize": 8,
                    "itemStyle": {{"color": "#1677ff"}},
                    "lineStyle": {{"width": 3}},
                    "areaStyle": {{"color": {{"type": "linear", "x": 0, "y": 0, "x2": 0, "y2": 1, "colorStops": [{{"offset": 0, "color": "rgba(22,119,255,0.2)"}}, {{"offset": 1, "color": "rgba(22,119,255,0)"}}]}}}}
                }}]
            }}
        }},
        {{
            "id": "chart_002",
            "title": "细分领域市场份额",
            "subtitle": "2024年各技术领域占比",
            "type": "horizontal_bar",
            "echarts_option": {{
                "grid": {{"left": "25%", "right": "15%", "top": "5%", "bottom": "5%"}},
                "xAxis": {{"type": "value", "show": false, "max": 100}},
                "yAxis": {{
                    "type": "category",
                    "data": ["计算机视觉", "自然语言处理", "机器学习平台", "智能语音", "其他"],
                    "axisLine": {{"show": false}},
                    "axisTick": {{"show": false}},
                    "axisLabel": {{"color": "#333", "fontSize": 13}}
                }},
                "series": [{{
                    "type": "bar",
                    "data": [
                        {{"value": 32, "itemStyle": {{"color": "#1677ff"}}}},
                        {{"value": 28, "itemStyle": {{"color": "#722ed1"}}}},
                        {{"value": 24, "itemStyle": {{"color": "#1677ff"}}}},
                        {{"value": 10, "itemStyle": {{"color": "#52c41a"}}}},
                        {{"value": 6, "itemStyle": {{"color": "#fa8c16"}}}}
                    ],
                    "barWidth": 12,
                    "label": {{
                        "show": true,
                        "position": "right",
                        "formatter": "{{c}}%",
                        "color": "#666"
                    }},
                    "backgroundStyle": {{"color": "#f5f5f5"}},
                    "showBackground": true
                }}]
            }}
        }}
    ]
}}
```"""

    def __init__(self, llm_api_key: str, llm_base_url: str, model: str = None):
        super().__init__(
            name="DataAnalyst",
            role="数据分析师",
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            model=model
        )

    async def process(self, state: ResearchState) -> ResearchState:
        """处理入口"""
        if state["phase"] == ResearchPhase.ANALYZING.value:
            return await self._analyze_data(state)
        return state

    async def _analyze_data(self, state: ResearchState) -> ResearchState:
        """执行数据分析"""
        self.logger.info("Starting data analysis...")

        # 发送开始事件
        self.add_message(state, "research_step", {
            "step_id": f"step_analyze_{uuid.uuid4().hex[:8]}",
            "step_type": "analyzing",
            "title": "数据分析",
            "subtitle": "生成可视化",
            "status": "running",
            "stats": {"results_count": 0, "charts_count": 0, "entities_count": 0}
        })

        # 一次模型调用同时提取数据、事实和实体关系；后续结构由 Python 构建。
        extracted_data = await self._extract_analysis_bundle(state)
        knowledge_graph = build_knowledge_graph(extracted_data, state.get("facts", []), state.get("query", ""))
        charts = ChartBuilder.build(extracted_data, state.get("facts", []))
        for point in extracted_data.get("data_points", []):
            if not any(existing.get("id") == point.get("id") for existing in state["data_points"]):
                state["data_points"].append(point)

        # 更新状态
        if knowledge_graph:
            state["knowledge_graph"] = knowledge_graph
            # 发送知识图谱事件
            self.add_message(state, "knowledge_graph", {
                "graph": knowledge_graph,
                "stats": {
                    "entities_count": len(knowledge_graph.get("nodes", [])),
                    "relations_count": len(knowledge_graph.get("edges", [])),
                    "entitiesCount": len(knowledge_graph.get("nodes", [])),
                    "relationsCount": len(knowledge_graph.get("edges", []))
                }
            })

        if charts:
            state["charts"].extend(charts)
            self.logger.info(f"[DataAnalyst] 生成了 {len(charts)} 个 ECharts 图表，准备发送 charts 事件")
            for i, chart in enumerate(charts):
                self.logger.info(f"[DataAnalyst] 图表 {i+1}: id={chart.get('id')}, title={chart.get('title')}, has_echarts_option={bool(chart.get('echarts_option'))}")
            # 发送图表事件
            self.add_message(state, "charts", {
                "charts": charts
            })
            self.logger.info(f"[DataAnalyst] ✅ charts 事件已发送")

        # 发送完成事件
        self.add_message(state, "research_step", {
            "step_type": "analyzing",
            "title": "数据分析",
            "subtitle": "生成可视化",
            "status": "completed",
            "stats": {
                "results_count": len(state.get("facts", [])),
                "charts_count": len(charts) if charts else 0,
                "entities_count": len(knowledge_graph.get("nodes", [])) if knowledge_graph else 0
            }
        })

        return state

    async def _extract_analysis_bundle(self, state: ResearchState) -> Dict[str, Any]:
        evidence_lines = []
        for fact in state.get("facts", [])[:30]:
            evidence_id = fact.get("evidence_id") or fact.get("id", "")
            evidence_lines.append(
                f"- [{evidence_id}] {fact.get('content', '')} | "
                f"{fact.get('source_name', '')} | {fact.get('source_url', '')}"
            )
        if not evidence_lines:
            return {key: [] for key in ("data_points", "time_series", "distributions", "facts", "entities", "relations", "insights")}
        response = await self.call_llm(
            system_prompt="你是数据与实体抽取器。严格依据证据，输出简洁 JSON。",
            user_prompt=self.COMBINED_EXTRACTION_PROMPT.format(
                query=state["query"], search_results="\n".join(evidence_lines)
            ),
            json_mode=True,
            temperature=0.1,
            max_tokens=5000,
            operation_name="extract_facts_data_entities",
        )
        result = self.parse_json_response(response)
        for data_point in result.get("data_points", []):
            state["data_points"].append(data_point)
        state["insights"].extend(result.get("insights", []))
        return result
