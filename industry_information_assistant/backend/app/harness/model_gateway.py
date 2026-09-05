"""Central model invocation boundary and metrics collector for agents."""

import asyncio
import contextvars
import hashlib
import json
import logging
import time
from collections import OrderedDict, defaultdict
from threading import Lock
from typing import Any, Dict, List, Optional

from openai import OpenAI

logger = logging.getLogger("Harness.ModelGateway")

_model_context: contextvars.ContextVar[Dict[str, str]] = contextvars.ContextVar(
    "model_gateway_context", default={}
)
_metrics: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
_metrics_lock = Lock()
_response_cache: "OrderedDict[str, Any]" = OrderedDict()
_MAX_CACHE_ENTRIES = 256


def set_model_context(**values: str) -> contextvars.Token:
    """Bind research/session metadata to all model calls in the current task."""
    current = dict(_model_context.get())
    current.update({key: value for key, value in values.items() if value})
    return _model_context.set(current)


def reset_model_context(token: contextvars.Token) -> None:
    _model_context.reset(token)


def get_model_metrics(research_id: str, clear: bool = False) -> List[Dict[str, Any]]:
    """Return a copy of recorded calls for one research run."""
    with _metrics_lock:
        rows = list(_metrics.get(research_id, []))
        if clear:
            _metrics.pop(research_id, None)
    return rows


def summarize_model_metrics(research_id: str) -> Dict[str, Any]:
    rows = get_model_metrics(research_id)
    by_agent: Dict[str, int] = defaultdict(int)
    for row in rows:
        by_agent[row["agent_name"]] += 1
    return {
        "total_llm_calls": len(rows),
        "calls_by_agent": dict(by_agent),
        "input_tokens": sum(row["input_tokens"] for row in rows),
        "output_tokens": sum(row["output_tokens"] for row in rows),
        "llm_duration_ms": sum(row["duration_ms"] for row in rows),
        "retry_count": sum(row["retry_count"] for row in rows),
        "cache_hits": sum(1 for row in rows if row["cache_hit"]),
        "failed_calls": sum(1 for row in rows if not row["success"]),
    }


class ModelGateway:
    """Owns model client construction and asynchronous completion calls."""

    def __init__(self, api_key: str, base_url: str, model: str):
        self.model = model
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    async def complete(self, *, metric_context: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Any:
        request: Dict[str, Any] = dict(kwargs)
        request.setdefault("model", self.model)
        context = {**_model_context.get(), **(metric_context or {})}
        cacheable = bool(request.pop("cacheable", True))
        cache_key = str(request.pop("cache_key", "") or "")
        if cacheable and not cache_key:
            cache_key = hashlib.sha256(
                json.dumps(request, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
        started = time.perf_counter()
        success = False
        error_type = ""
        response = None
        try:
            if cacheable and cache_key:
                with _metrics_lock:
                    response = _response_cache.get(cache_key)
                    if response is not None:
                        _response_cache.move_to_end(cache_key)
                if response is not None:
                    context["cache_hit"] = True
                    success = True
                    return response
            response = await asyncio.to_thread(self.client.chat.completions.create, **request)
            success = True
            if cacheable and cache_key:
                with _metrics_lock:
                    _response_cache[cache_key] = response
                    _response_cache.move_to_end(cache_key)
                    while len(_response_cache) > _MAX_CACHE_ENTRIES:
                        _response_cache.popitem(last=False)
            return response
        except Exception as exc:
            error_type = type(exc).__name__
            raise
        finally:
            duration_ms = int((time.perf_counter() - started) * 1000)
            usage = getattr(response, "usage", None)
            row = {
                "agent_name": context.get("agent_name", "unknown"),
                "operation_name": context.get("operation_name", "complete"),
                "model": request.get("model", self.model),
                "input_tokens": 0 if context.get("cache_hit") else int(getattr(usage, "prompt_tokens", 0) or 0),
                "output_tokens": 0 if context.get("cache_hit") else int(getattr(usage, "completion_tokens", 0) or 0),
                "duration_ms": duration_ms,
                "retry_count": int(context.get("retry_count", 0) or 0),
                "success": success,
                "error_type": error_type,
                "cache_hit": bool(context.get("cache_hit", False)),
                "research_id": context.get("research_id", ""),
                "session_id": context.get("session_id", ""),
            }
            research_id = row["research_id"]
            if research_id:
                with _metrics_lock:
                    _metrics[research_id].append(row)
            logger.info("model_call_metric=%s", row)
