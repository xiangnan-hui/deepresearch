"""不阻塞 Slow Worker 的轻量研究对话与 steering Agent。"""

import asyncio
import json
import re
from typing import Any, Dict, List, Optional

try:
    from config.settings import settings
except ImportError:
    from app.config.settings import settings

from .models import CommandType


class FastResearchAgent:
    """规则处理明确意图，小模型仅处理复杂语义问答。"""

    def __init__(self, states: Any, commands: Any):
        self.states = states
        self.commands = commands
        self._gateway: Optional[Any] = None
        if settings.dashscope_api_key:
            try:
                try:
                    from harness.model_gateway import ModelGateway
                except ImportError:
                    from app.harness.model_gateway import ModelGateway
                self._gateway = ModelGateway(
                    api_key=settings.dashscope_api_key,
                    base_url=settings.chat_base_url,
                    model=settings.chat_model,
                )
            except ImportError:
                self._gateway = None

    async def respond(self, research_id: str, question: str) -> Dict[str, Any]:
        state = await self.states.get(research_id)
        if not state:
            raise KeyError(research_id)
        question = question.strip()

        command = self._rule_command(question)
        if command:
            command_type, payload, answer = command
            accepted = await self.commands.publish(research_id, command_type, payload)
            return {"intent": command_type.value, "answer": answer, "command": accepted}

        if self._is_status_query(question):
            return {"intent": "STATUS_QUERY", "answer": self._status_answer(state)}

        if self._is_evidence_query(question):
            return {"intent": "FINDING_QUERY", "answer": self._evidence_answer(state, question)}

        model_result = await self._semantic_response(state, question)
        if model_result:
            command_name = model_result.get("command_type")
            payload = model_result.get("command_payload") or {}
            if command_name:
                try:
                    command_type = CommandType(command_name)
                    accepted = await self.commands.publish(research_id, command_type, payload)
                    model_result["command"] = accepted
                except ValueError:
                    pass
            return {
                "intent": model_result.get("intent", "GENERAL_CHAT"),
                "answer": model_result.get("answer") or self._status_answer(state),
                "command": model_result.get("command"),
            }

        return {"intent": "GENERAL_CHAT", "answer": self._context_fallback(state, question)}

    @staticmethod
    def _rule_command(question: str):
        if re.search(r"(取消|停止|终止).{0,4}研究", question):
            return CommandType.CANCEL, {}, "已提交取消请求，研究将在下一个安全点停止。"
        if re.search(r"(暂停|先停).{0,4}研究|先暂停", question):
            return CommandType.PAUSE, {}, "已提交暂停请求，研究将在下一个安全点暂停。"
        if re.search(r"(继续|恢复).{0,4}研究", question):
            return CommandType.RESUME, {}, "已提交恢复请求。"
        if re.search(r"(只看|改为|改成|转向|聚焦到|限定为)", question):
            return (
                CommandType.CHANGE_DIRECTION,
                {"direction": question},
                "已记录新的研究方向，将在当前安全步骤结束后重新规划。",
            )
        if re.search(r"(重点|着重|优先).{0,6}(研究|关注|分析)|增加|补充|同时关注", question):
            return (
                CommandType.ADD_CONSTRAINT,
                {"constraint": question},
                "已加入这项研究要求，后台将在下一个安全点更新计划并优先处理。",
            )
        return None

    @staticmethod
    def _is_status_query(question: str) -> bool:
        return bool(re.search(r"(到哪|进度|哪一步|研究状态|还要多久|完成了吗)", question))

    @staticmethod
    def _is_evidence_query(question: str) -> bool:
        return bool(re.search(r"(事实|发现|结论|证据|来源|搜索结果|靠谱吗|可信)", question))

    @staticmethod
    def _status_answer(state: Dict[str, Any]) -> str:
        digest = state.get("research_digest", {})
        return (
            f"研究状态：{state.get('status')}，进度约 {state.get('progress', 0)}%。\n"
            f"当前阶段：{state.get('current_stage') or '尚未开始'}；"
            f"当前步骤：{state.get('current_step') or '正在处理阶段内部任务'}。\n"
            f"{digest.get('summary', '')}"
        )

    def _evidence_answer(self, state: Dict[str, Any], question: str) -> str:
        confirmed = [x for x in state.get("confirmed_findings", []) if x.get("status") == "active"]
        tentative = [x for x in state.get("tentative_findings", []) if x.get("status") == "active"]
        findings = confirmed + tentative
        step_match = re.search(r"step\s*(\d+)", question, re.IGNORECASE)
        if step_match:
            sequence = int(step_match.group(1))
            findings = [x for x in findings if x.get("event_sequence") == sequence]
        findings = sorted(findings, key=lambda x: self._relevance(question, str(x.get("content", ""))), reverse=True)
        selected = findings[:5]
        if not selected:
            results = sorted(
                state.get("recent_search_results", []),
                key=lambda x: self._relevance(question, f"{x.get('title', '')} {x.get('snippet', '')}"),
                reverse=True,
            )[:5]
            if not results:
                return "当前共享研究上下文中还没有与这个问题匹配的事实或搜索结果。"
            return "当前相关搜索结果（尚未完成事实验证）：\n" + "\n".join(
                f"{i}. {x.get('title', '未命名来源')}：{x.get('snippet', '')[:180]}（{x.get('url', '')}）"
                for i, x in enumerate(results, 1)
            )
        confirmed_ids = {x.get("id") for x in confirmed}
        return "当前匹配的研究事实：\n" + "\n".join(
            f"{i}. [{'已确认' if x.get('id') in confirmed_ids else '待验证'}] "
            f"{x.get('content', '')}（来源：{x.get('source_name') or x.get('source_url') or '待整理'}）"
            for i, x in enumerate(selected, 1)
        )

    async def _semantic_response(self, state: Dict[str, Any], question: str) -> Optional[Dict[str, Any]]:
        if not self._gateway:
            return None
        context = self._compact_context(state)
        prompt = f"""你是正在运行的 Deep Research 的快速对话协调员。只能依据给定研究上下文回答，不能联网，也不能声称未发生的事实。
如果用户是在追加要求或改变方向，选择相应 command_type；普通讨论则不发送命令。
可用命令：ADD_CONSTRAINT、ADD_QUESTION、CHANGE_DIRECTION、PRIORITIZE_GAP。没有命令时为 null。

研究上下文：
{context}

用户消息：{question}

只输出 JSON：
{{"intent":"GENERAL_CHAT/FINDING_QUERY/ADD_CONSTRAINT/ADD_QUESTION/CHANGE_DIRECTION/PRIORITIZE_GAP","answer":"简洁自然的中文回答","command_type":null,"command_payload":{{}}}}"""
        try:
            response = await asyncio.wait_for(
                self._gateway.complete(
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0.1,
                    max_tokens=600,
                    response_format={"type": "json_object"},
                    timeout=6,
                ),
                timeout=7,
            )
            content = response.choices[0].message.content or "{}"
            return json.loads(content)
        except Exception:
            return None

    @staticmethod
    def _compact_context(state: Dict[str, Any]) -> str:
        digest = state.get("research_digest", {})
        findings = state.get("confirmed_findings", [])[-8:] + state.get("tentative_findings", [])[-8:]
        results = state.get("recent_search_results", [])[-10:]
        return json.dumps({
            "status": state.get("status"),
            "stage": state.get("current_stage"),
            "step": state.get("current_step"),
            "progress": state.get("progress"),
            "digest": digest,
            "constraints": state.get("user_constraints", []),
            "findings": findings,
            "search_results": results,
        }, ensure_ascii=False, default=str)[:12000]

    @staticmethod
    def _relevance(query: str, text: str) -> int:
        normalized_query = re.sub(r"[\s，。！？、：；,.!?]", "", query.lower())
        normalized_text = text.lower()
        tokens = set(re.findall(r"[a-z0-9_-]+|[\u4e00-\u9fff]{2,8}", normalized_query))
        score = sum(3 for token in tokens if token in normalized_text)
        score += sum(1 for i in range(max(0, len(normalized_query) - 1)) if normalized_query[i:i + 2] in normalized_text)
        return score

    def _context_fallback(self, state: Dict[str, Any], question: str) -> str:
        evidence = self._evidence_answer(state, question)
        if "还没有" not in evidence:
            return evidence
        return self._status_answer(state) + "\n当前上下文不足以准确回答该问题，我已避免凭空补充。"
