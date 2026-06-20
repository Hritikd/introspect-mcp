"""Core introspection engine.

This module is deliberately free of any MCP dependency so it can be unit-tested
and reused on its own. It answers one question for every public Python object
that is *actually installed* in the current environment:

    "What is the real signature / docstring / source / location of this thing?"

Everything here is read-only. Resolving a dotted name imports the relevant
module (this is inherent to Python introspection — there is no way to read a
live signature without importing), but nothing is ever mutated, written, or
executed beyond normal import side effects.
"""

from __future__ import annotations

import difflib
import importlib
import importlib.metadata
import inspect
import pkgutil
from dataclasses import dataclass, field
from functools import lru_cache
from types import ModuleType
from typing import Any

__all__ = [
    "ResolveError",
    "ResolvedSymbol",
    "resolve",
    "lookup_symbol",
    "get_signature",
    "get_source",
    "list_members",
    "search_symbols",
    "package_version",
]


class ResolveError(Exception):
    """Raised when a dotted name cannot be resolved to a live object."""


@dataclass
class ResolvedSymbol:
    """A successfully resolved Python object plus useful metadata."""

    name: str
    obj: Any
    kind: str
    module: str | None = None
    qualname: str | None = None
    extras: dict[str, Any] = field(default_factory=dict)


def _kind_of(obj: Any) -> str:
    if inspect.ismodule(obj):
        return "module"
    if inspect.isclass(obj):
        return "class"
    if inspect.isfunction(obj):
        return "function"
    if inspect.ismethod(obj):
        return "method"
    if inspect.isbuiltin(obj):
        return "builtin"
    if isinstance(obj, (staticmethod, classmethod)):
        return "method"
    if inspect.isroutine(obj):
        return "function"
    return type(obj).__name__


@lru_cache(maxsize=512)
def resolve(name: str) -> ResolvedSymbol:
    """Resolve a dotted name (``pandas.DataFrame.merge``) to a live object.

    Strategy: import the longest importable module prefix, then walk the
    remaining attributes with ``getattr``. This transparently handles
    ``os.path.join`` (where ``os.path`` is a module) as well as
    ``collections.OrderedDict.move_to_end`` (attribute chains on a class).
    """
    if not name or not all(part.isidentifier() for part in name.split(".")):
        raise ResolveError(f"{name!r} is not a valid dotted Python name.")

    parts = name.split(".")
    module = None
    module_path = ""

    # Import the longest prefix that is an importable module.
    for i in range(len(parts), 0, -1):
        candidate = ".".join(parts[:i])
        try:
            module = importlib.import_module(candidate)
            module_path = candidate
            remaining = parts[i:]
            break
        except ModuleNotFoundError:
            continue
        except Exception as exc:  # noqa: BLE001 - surface real import failures
            raise ResolveError(
                f"Importing {candidate!r} failed: {type(exc).__name__}: {exc}"
            ) from exc
    else:
        raise ResolveError(
            f"No importable module found for {name!r}. "
            f"Is the package installed in this environment?"
        )

    obj: Any = module
    walked = module_path
    for attr in remaining:
        try:
            obj = getattr(obj, attr)
        except AttributeError as exc:
            raise ResolveError(
                f"{walked!r} has no attribute {attr!r} "
                f"(installed version may differ from what you expected)."
            ) from exc
        walked = f"{walked}.{attr}"

    return ResolvedSymbol(
        name=name,
        obj=obj,
        kind=_kind_of(obj),
        module=getattr(obj, "__module__", module_path),
        qualname=getattr(obj, "__qualname__", None),
    )


def _safe_signature(obj: Any) -> str | None:
    try:
        return str(inspect.signature(obj))
    except (ValueError, TypeError):
        return None


def _location(obj: Any) -> str | None:
    try:
        file = inspect.getsourcefile(obj) or inspect.getfile(obj)
    except TypeError:
        return None
    try:
        _, line = inspect.getsourcelines(obj)
    except (OSError, TypeError):
        return file
    return f"{file}:{line}"


def _first_doc_line(obj: Any) -> str | None:
    doc = inspect.getdoc(obj)
    if not doc:
        return None
    return doc.strip().splitlines()[0]


def lookup_symbol(name: str) -> dict[str, Any]:
    """Return a compact, agent-friendly summary of a symbol.

    This is the most useful single call for an agent: kind, real signature,
    one-line doc, defining module, and source location — without dumping a
    whole file into the context window.
    """
    sym = resolve(name)
    info: dict[str, Any] = {
        "name": sym.name,
        "kind": sym.kind,
        "module": sym.module,
        "qualname": sym.qualname,
        "signature": None,
        "summary": _first_doc_line(sym.obj),
        "location": _location(sym.obj),
    }

    if sym.kind in {"class"}:
        init = getattr(sym.obj, "__init__", None)
        info["signature"] = _safe_signature(sym.obj) or _safe_signature(init)
        # Surface a handful of public methods so the agent knows what exists.
        info["public_members"] = [
            n for n in dir(sym.obj) if not n.startswith("_")
        ][:40]
    elif sym.kind in {"function", "method", "builtin"}:
        info["signature"] = _safe_signature(sym.obj)
    elif sym.kind == "module":
        info["public_members"] = [
            n for n in dir(sym.obj) if not n.startswith("_")
        ][:60]
    else:
        info["type"] = type(sym.obj).__name__
        info["repr"] = _truncate(repr(sym.obj), 200)

    pkg = (sym.module or name).split(".")[0]
    info["package"] = pkg
    info["package_version"] = _try_version(pkg)
    return info


def get_signature(name: str) -> str:
    """Return just the call signature, e.g. ``merge(right, how='inner', ...)``."""
    sym = resolve(name)
    target = sym.obj
    if sym.kind == "class":
        sig = _safe_signature(target) or _safe_signature(
            getattr(target, "__init__", None)
        )
    else:
        sig = _safe_signature(target)
    if sig is None:
        doc1 = _first_doc_line(target)
        raise ResolveError(
            f"No introspectable signature for {name!r} "
            f"(likely a C extension). First doc line: {doc1 or 'n/a'}"
        )
    display = sym.qualname or sym.name.split(".")[-1]
    return f"{display}{sig}"


def get_source(name: str, max_chars: int = 20_000) -> str:
    """Return the real source code of a function/class/method/module."""
    sym = resolve(name)
    try:
        src = inspect.getsource(sym.obj)
    except (OSError, TypeError) as exc:
        doc = inspect.getdoc(sym.obj)
        raise ResolveError(
            f"Source unavailable for {name!r} ({type(exc).__name__}); "
            f"it is likely implemented in C. Docstring:\n\n{doc or '(none)'}"
        ) from exc
    loc = _location(sym.obj)
    header = f"# {name}  ({sym.kind})\n# {loc}\n\n" if loc else ""
    body = src if len(src) <= max_chars else src[:max_chars] + "\n# ... [truncated]"
    return header + body


def list_members(name: str, include_private: bool = False) -> dict[str, Any]:
    """List the members of a module or class with their kinds and signatures."""
    sym = resolve(name)
    if sym.kind not in {"module", "class"}:
        raise ResolveError(
            f"{name!r} is a {sym.kind}; list_members works on modules and classes."
        )

    members: list[dict[str, Any]] = []
    for attr in sorted(dir(sym.obj)):
        if not include_private and attr.startswith("_"):
            continue
        try:
            member = getattr(sym.obj, attr)
        except Exception:  # noqa: BLE001 - some attrs raise on access
            continue
        members.append(
            {
                "name": attr,
                "kind": _kind_of(member),
                "signature": _safe_signature(member),
                "summary": _first_doc_line(member),
            }
        )
    return {"name": name, "kind": sym.kind, "count": len(members), "members": members}


@lru_cache(maxsize=128)
def _index_package(package: str, max_symbols: int = 4000) -> tuple[str, ...]:
    """Build a flat list of public dotted symbol names for a package.

    Walks the package's submodules one level deep via ``pkgutil`` and collects
    public top-level attributes from each. Bounded and cached for speed.
    """
    try:
        root = importlib.import_module(package)
    except Exception as exc:  # noqa: BLE001
        raise ResolveError(
            f"Cannot import package {package!r}: {type(exc).__name__}: {exc}"
        ) from exc

    names: set[str] = set()

    def harvest(mod: ModuleType, prefix: str) -> None:
        exported = getattr(mod, "__all__", None)
        attrs = exported if exported else [a for a in dir(mod) if not a.startswith("_")]
        for a in attrs:
            if isinstance(a, str) and a.isidentifier():
                names.add(f"{prefix}.{a}")

    harvest(root, package)

    path = getattr(root, "__path__", None)
    if path:
        for info in pkgutil.iter_modules(path):
            if info.name.startswith("_"):
                continue
            sub_name = f"{package}.{info.name}"
            try:
                sub = importlib.import_module(sub_name)
            except Exception:  # noqa: BLE001 - skip submodules that fail to import
                names.add(sub_name)
                continue
            names.add(sub_name)
            harvest(sub, sub_name)
            if len(names) >= max_symbols:
                break

    return tuple(sorted(names)[:max_symbols])


def search_symbols(
    query: str, package: str | None = None, limit: int = 20
) -> dict[str, Any]:
    """Fuzzy-search for symbol names, optionally scoped to one package.

    Useful when the agent half-remembers a name: ``search_symbols("read csv",
    package="pandas")`` surfaces ``pandas.read_csv``.
    """
    if package is None:
        package = query.split(".")[0].split()[0] if query else ""
        if not package:
            raise ResolveError("Provide a package to scope the search.")

    candidates = _index_package(package)
    needle = query.lower().replace(" ", "")

    scored: list[tuple[float, str]] = []
    for full in candidates:
        leaf = full.split(".")[-1].lower()
        if needle in full.lower() or needle in leaf:
            score = 1.0
        else:
            score = difflib.SequenceMatcher(None, needle, leaf).ratio()
        scored.append((score, full))

    scored.sort(key=lambda t: (-t[0], len(t[1])))
    hits = [{"name": n, "score": round(s, 3)} for s, n in scored[:limit] if s > 0.4]
    return {"query": query, "package": package, "count": len(hits), "results": hits}


def package_version(name: str) -> dict[str, Any]:
    """Return the installed version and location of a package."""
    top = name.split(".")[0]
    version = _try_version(top)
    location = None
    try:
        mod = importlib.import_module(top)
        location = getattr(mod, "__file__", None) or str(
            getattr(mod, "__path__", "")
        )
    except Exception:  # noqa: BLE001
        pass
    if version is None and location is None:
        raise ResolveError(f"Package {top!r} is not installed in this environment.")
    return {"package": top, "version": version, "location": location}


def _try_version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None
    except Exception:  # noqa: BLE001
        return None


def _truncate(text: str, n: int) -> str:
    return text if len(text) <= n else text[:n] + "…"
