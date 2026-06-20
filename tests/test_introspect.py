"""Tests for the introspection engine.

These deliberately target the standard library (json, collections, pathlib,
os.path, textwrap) so they are fully deterministic on any machine and in CI —
no third-party packages required.
"""

from __future__ import annotations

import pytest

from introspect_mcp import introspect
from introspect_mcp.introspect import ResolveError

# ---------------------------------------------------------------- resolve()

def test_resolve_module():
    sym = introspect.resolve("json")
    assert sym.kind == "module"
    assert sym.obj.__name__ == "json"


def test_resolve_function_in_module():
    sym = introspect.resolve("json.dumps")
    assert sym.kind == "function"
    assert sym.name == "json.dumps"


def test_resolve_class():
    sym = introspect.resolve("collections.OrderedDict")
    assert sym.kind == "class"


def test_resolve_method_on_class():
    # Attribute chain across a class -> method/function.
    sym = introspect.resolve("collections.OrderedDict.move_to_end")
    assert sym.kind in {"function", "method", "builtin"}


def test_resolve_dotted_submodule():
    # os.path is itself a module, reached via attribute on os.
    sym = introspect.resolve("os.path.join")
    assert sym.kind in {"function", "builtin"}


def test_resolve_unknown_package_raises():
    with pytest.raises(ResolveError):
        introspect.resolve("definitely_not_a_real_package_xyz")


def test_resolve_missing_attribute_raises():
    with pytest.raises(ResolveError):
        introspect.resolve("json.this_attr_does_not_exist")


def test_resolve_invalid_name_raises():
    with pytest.raises(ResolveError):
        introspect.resolve("not a name!")


# ---------------------------------------------------------- lookup_symbol()

def test_lookup_function_has_signature_and_summary():
    info = introspect.lookup_symbol("json.dumps")
    assert info["kind"] == "function"
    assert "obj" in info["signature"]  # json.dumps(obj, ...)
    assert info["summary"]  # docstring first line present


def test_lookup_class_lists_public_members():
    info = introspect.lookup_symbol("collections.OrderedDict")
    assert info["kind"] == "class"
    assert "move_to_end" in info["public_members"]


def test_lookup_reports_package_and_version_keys():
    info = introspect.lookup_symbol("json.dumps")
    assert info["package"] == "json"
    assert "package_version" in info  # stdlib -> may be None, key still present


# ----------------------------------------------------------- get_signature()

def test_get_signature_renders_name_and_params():
    sig = introspect.get_signature("textwrap.fill")
    assert sig.startswith("fill(")
    assert "text" in sig


def test_get_signature_for_class_uses_init():
    sig = introspect.get_signature("collections.OrderedDict")
    assert "(" in sig  # some signature was produced


# -------------------------------------------------------------- get_source()

def test_get_source_returns_real_code():
    src = introspect.get_source("textwrap.fill")
    assert "def fill" in src
    assert "# textwrap.fill" in src  # header injected


def test_get_source_c_extension_raises_with_doc():
    # len() is a C builtin: no Python source available.
    with pytest.raises(ResolveError):
        introspect.get_source("builtins.len")


# ------------------------------------------------------------ list_members()

def test_list_members_of_class():
    out = introspect.list_members("pathlib.PurePath")
    names = {m["name"] for m in out["members"]}
    assert "name" in names or "parts" in names
    assert out["count"] > 0


def test_list_members_rejects_function():
    with pytest.raises(ResolveError):
        introspect.list_members("json.dumps")


def test_list_members_private_toggle():
    public = introspect.list_members("json", include_private=False)
    everything = introspect.list_members("json", include_private=True)
    assert everything["count"] >= public["count"]


# ---------------------------------------------------------- search_symbols()

def test_search_finds_known_symbol():
    out = introspect.search_symbols("OrderedDict", package="collections")
    names = {r["name"] for r in out["results"]}
    assert any("OrderedDict" in n for n in names)


def test_search_scopes_to_package():
    out = introspect.search_symbols("dump", package="json")
    assert out["package"] == "json"
    assert all(r["name"].startswith("json") for r in out["results"])


# --------------------------------------------------------- package_version()

def test_package_version_for_stdlib_returns_location():
    out = introspect.package_version("json")
    assert out["package"] == "json"
    assert out["location"]  # on-disk path present


def test_package_version_unknown_raises():
    with pytest.raises(ResolveError):
        introspect.package_version("definitely_not_a_real_package_xyz")
