"""introspect-mcp — ground-truth Python API reference for AI coding agents.

An MCP server that introspects the *exact* package versions installed in your
project and hands your agent real signatures, docstrings, and source — so it
stops hallucinating APIs.
"""

from .introspect import (
    ResolveError,
    get_signature,
    get_source,
    list_members,
    lookup_symbol,
    package_version,
    search_symbols,
)

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ResolveError",
    "get_signature",
    "get_source",
    "list_members",
    "lookup_symbol",
    "package_version",
    "search_symbols",
]
