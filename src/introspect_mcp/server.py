"""MCP server exposing the introspection engine as tools.

Run it directly for a quick sanity check::

    python -m introspect_mcp

or wire it into an MCP client (Claude Code, Cursor, …) — see the README.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import introspect
from .introspect import ResolveError

mcp = FastMCP(
    "introspect",
    instructions=(
        "Ground-truth Python API reference for the packages installed in THIS "
        "project. Before writing code that calls a third-party library, use these "
        "tools to confirm the real signature, members, or source instead of "
        "guessing from memory — the installed version may differ from your "
        "training data. All tools are read-only."
    ),
)


def _ok(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str)


def _err(exc: Exception) -> str:
    return _ok({"error": str(exc), "type": type(exc).__name__})


@mcp.tool()
def lookup_symbol(name: str) -> str:
    """Summarize a Python symbol: kind, real signature, one-line doc, members,
    defining module, source location, and installed package version.

    Use this first. ``name`` is a dotted path to anything installed, e.g.
    ``pandas.read_csv``, ``fastapi.FastAPI``, ``requests.Session.get``.
    """
    try:
        return _ok(introspect.lookup_symbol(name))
    except ResolveError as exc:
        return _err(exc)


@mcp.tool()
def get_signature(name: str) -> str:
    """Return only the exact call signature of a function/method/class.

    Example: ``get_signature("pandas.DataFrame.merge")`` →
    ``merge(right, how='inner', on=None, ...)`` for the installed version.
    """
    try:
        return introspect.get_signature(name)
    except ResolveError as exc:
        return _err(exc)


@mcp.tool()
def get_source(name: str, max_chars: int = 20000) -> str:
    """Return the real source code of a function/class/method/module from the
    installed package — the actual implementation, not a guess."""
    try:
        return introspect.get_source(name, max_chars=max_chars)
    except ResolveError as exc:
        return _err(exc)


@mcp.tool()
def list_members(name: str, include_private: bool = False) -> str:
    """List members of a module or class with their kinds and signatures.

    Example: ``list_members("pathlib.Path")`` enumerates the methods that
    actually exist on Path in this environment.
    """
    try:
        return _ok(introspect.list_members(name, include_private=include_private))
    except ResolveError as exc:
        return _err(exc)


@mcp.tool()
def search_symbols(query: str, package: str = "", limit: int = 20) -> str:
    """Fuzzy-search for a symbol when you only half-remember the name.

    Example: ``search_symbols("read csv", package="pandas")`` →
    ``pandas.read_csv``. If ``package`` is empty, the first token of the query
    is used as the package to scope the search.
    """
    try:
        return _ok(
            introspect.search_symbols(query, package=package or None, limit=limit)
        )
    except ResolveError as exc:
        return _err(exc)


@mcp.tool()
def package_version(name: str) -> str:
    """Return the installed version and on-disk location of a package."""
    try:
        return _ok(introspect.package_version(name))
    except ResolveError as exc:
        return _err(exc)


def main() -> None:
    """Console-script / module entrypoint. Speaks MCP over stdio."""
    mcp.run()


if __name__ == "__main__":
    main()
