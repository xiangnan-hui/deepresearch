

"""Service package with compatibility-preserving lazy exports."""

from importlib import import_module

_EXPORTS = {
    "DocumentService": ("document_service", "DocumentService"),
    "ServiceConfig": ("config", "ServiceConfig"),
    "WebSearchService": ("web_search_service", "WebSearchService"),
    "ChatService": ("chat_service", "ChatService"),
    "SessionService": ("session_service", "SessionService"),
    "Text2SQLService": ("text2sql_service", "Text2SQLService"),
    "create_text2sql_service": ("text2sql_service", "create_text2sql_service"),
}

__all__ = list(_EXPORTS)


def __getattr__(name):
    if name not in _EXPORTS:
        raise AttributeError(name)
    module_name, attribute = _EXPORTS[name]
    value = getattr(import_module(f"{__name__}.{module_name}"), attribute)
    globals()[name] = value
    return value
