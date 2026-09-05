"""Canonical Python-native evidence models and adapters."""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit


def normalize_url(value: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        parts = urlsplit(value)
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), parts.query, ""))
    except ValueError:
        return value


@dataclass
class Evidence:
    evidence_id: str
    content: str
    source_url: str = ""
    source_name: str = ""
    published_at: Optional[str] = None
    source_type: str = "unknown"
    credibility_score: float = 0.5
    related_sections: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class EvidenceAdapter:
    """Map heterogeneous tool results without asking an LLM to reshape them."""

    @staticmethod
    def from_mapping(item: Dict[str, Any], related_sections: Optional[List[str]] = None) -> Evidence:
        content = str(item.get("content") or item.get("snippet") or item.get("summary") or item.get("description") or "").strip()
        url = normalize_url(str(item.get("source_url") or item.get("url") or item.get("link") or ""))
        name = str(item.get("source_name") or item.get("site_name") or item.get("source") or item.get("title") or "").strip()
        published = item.get("published_at") or item.get("published_date") or item.get("date")
        digest = sha256(f"{url}\n{content}".encode("utf-8")).hexdigest()[:16]
        hostname = urlsplit(url).netloc.lower()
        source_type = str(item.get("source_type") or "unknown")
        credibility = float(item.get("credibility_score", item.get("score", 0.5)) or 0.5)
        if source_type == "unknown":
            if hostname.endswith((".gov", ".gov.cn")):
                source_type, credibility = "official", max(credibility, 0.9)
            elif hostname.endswith(("arxiv.org", ".edu", ".ac.cn")):
                source_type, credibility = "academic", max(credibility, 0.85)
            elif any(domain in hostname for domain in ("idc.com", "gartner.com", "nvidia.com", "ibm.com", "openai.com", "anthropic.com", "deepseek.com")):
                source_type, credibility = "official", max(credibility, 0.85)
            elif any(domain in hostname for domain in ("csdn.net", "juejin.cn", "cnblogs.com")):
                source_type, credibility = "self_media", min(credibility, 0.45)
        return Evidence(
            evidence_id=str(item.get("evidence_id") or item.get("id") or f"ev_{digest}"),
            content=content,
            source_url=url,
            source_name=name,
            published_at=str(published) if published else None,
            source_type=source_type,
            credibility_score=credibility,
            related_sections=list(item.get("related_sections") or related_sections or []),
            metadata=dict(item.get("metadata") or {}),
        )

    @classmethod
    def normalize_many(cls, items: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        unique: Dict[str, Evidence] = {}
        for item in items:
            evidence = cls.from_mapping(item)
            key = evidence.source_url or sha256(evidence.content.encode("utf-8")).hexdigest()
            if key and key not in unique:
                unique[key] = evidence
        return [evidence.to_dict() for evidence in unique.values()]
