"""Registries provide explicit capability boundaries for the harness."""

from typing import Any, Dict, Iterable


class CapabilityRegistry:
    def __init__(self) -> None:
        self._items: Dict[str, Any] = {}

    def register(self, name: str, capability: Any) -> None:
        if not name:
            raise ValueError("capability name cannot be empty")
        self._items[name] = capability

    def get(self, name: str) -> Any:
        if name not in self._items:
            raise KeyError(f"capability is not registered: {name}")
        return self._items[name]

    def names(self) -> Iterable[str]:
        return tuple(self._items)


class ToolRegistry(CapabilityRegistry):
    pass


class SkillRegistry(CapabilityRegistry):
    pass
