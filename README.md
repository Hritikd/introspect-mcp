<div align="center">

# introspect-mcp

**Stop your AI coding agent from hallucinating APIs.**

An [MCP](https://modelcontextprotocol.io) server that introspects the *exact* package
versions installed in **your** project and hands the agent real signatures,
docstrings, and source code — so it stops guessing from stale training data.

[![CI](https://github.com/Hritikd/introspect-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Hritikd/introspect-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![MCP](https://img.shields.io/badge/MCP-server-purple)](https://modelcontextprotocol.io)

</div>

---

## The problem

Your AI coding agent — Claude Code, Cursor, Windsurf, Cline — writes code by predicting
tokens from its training data. So it does this constantly:

- Calls a method that **was renamed three versions ago**.
- Passes a keyword argument that **doesn't exist in the version you have installed**.
- Invents a function that **sounds right but was never real**.
- Confidently uses an API from a library's `2.x` docs when your `pyproject.toml` pins `1.x`.

You only find out when the code crashes. The agent had no way to know — it never looked
at what's *actually installed*.

## The fix

`introspect-mcp` gives the agent a set of tools to look up the **ground truth** from the
Python environment your project actually runs in:

```text
agent: I'll call pandas.DataFrame.append() to add the row...
  └─ get_signature("pandas.DataFrame.append")
       → error: 'pandas.DataFrame' has no attribute 'append'
         (installed version may differ from what you expected.)
agent: Right — append() was removed in pandas 2.0. I'll use pd.concat instead.
  └─ get_signature("pandas.concat")
       → concat(objs, *, axis=0, join='inner', ignore_index=False, ...)
agent: ✓ writes correct, version-exact code on the first try.
```

No API keys. No network. No config beyond pointing your client at it. It reads the code
sitting in your virtualenv.

> **Think of it as the offline, private, version-exact sibling of [Context7](https://github.com/upstash/context7).**
> Context7 fetches documentation from the web. `introspect-mcp` reads the *real source* of
> the exact versions installed in your project — works offline, never leaks your code, and
> is always in sync with what you'll actually run.

---

## Install

### Claude Code

```bash
claude mcp add introspect -- uvx introspect-mcp
```

Or, while the package is being published to PyPI, run it straight from this repo:

```bash
claude mcp add introspect -- uvx --from git+https://github.com/Hritikd/introspect-mcp introspect-mcp
```

### Cursor / Windsurf / any MCP client

Add this to your MCP config (`~/.cursor/mcp.json`, `mcp_config.json`, etc.):

```json
{
  "mcpServers": {
    "introspect": {
      "command": "uvx",
      "args": ["introspect-mcp"]
    }
  }
}
```

> **Important:** run the server with the **same Python environment as your project** so it
> sees your installed dependencies. The simplest way is to install it into your project's
> venv and point the client at that interpreter:
>
> ```json
> {
>   "mcpServers": {
>     "introspect": {
>       "command": "/path/to/your/project/.venv/bin/python",
>       "args": ["-m", "introspect_mcp"]
>     }
>   }
> }
> ```
>
> See [`examples/`](examples/) for ready-to-copy configs.

### Quick sanity check

```bash
uvx introspect-mcp        # starts the stdio server (Ctrl-C to exit)
# or, from a clone:
pip install -e ".[dev]" && python -m introspect_mcp
```

---

## Tools

| Tool | What it answers |
|------|-----------------|
| `lookup_symbol(name)` | One-shot summary: kind, **real signature**, one-line doc, members, defining module, source location, installed version. *Start here.* |
| `get_signature(name)` | Just the exact call signature for the installed version. |
| `get_source(name)` | The **real source code** of a function / class / method / module. |
| `list_members(name)` | Every member of a module or class, with kinds and signatures. |
| `search_symbols(query, package)` | Fuzzy-find a symbol you half-remember (`"read csv"` → `pandas.read_csv`). |
| `package_version(name)` | Installed version + on-disk location of a package. |

`name` is always a dotted path to anything importable in your environment:
`requests.get`, `fastapi.FastAPI`, `pathlib.Path.glob`, `numpy.linalg.norm`.

### Example responses

```jsonc
// lookup_symbol("pathlib.Path.glob")
{
  "name": "pathlib.Path.glob",
  "kind": "function",
  "signature": "(self, pattern, *, case_sensitive=None)",
  "summary": "Iterate over this subtree and yield all existing files ...",
  "location": "/usr/lib/python3.12/pathlib.py:1056",
  "package": "pathlib",
  "package_version": null
}
```

```text
// get_signature("json.dumps")
dumps(obj, *, skipkeys=False, ensure_ascii=True, check_circular=True, ...)
```

---

## How it works

```
            ┌─────────────────┐   MCP (stdio)   ┌──────────────────────┐
  AI agent  │  Claude Code /  │ ───────────────▶│   introspect-mcp     │
  (client)  │  Cursor / Cline │ ◀───────────────│   (this server)      │
            └─────────────────┘   tool result   └──────────┬───────────┘
                                                            │ importlib + inspect + ast
                                                            ▼
                                              ┌──────────────────────────┐
                                              │  YOUR project's venv      │
                                              │  (the exact installed     │
                                              │   versions of every dep)  │
                                              └──────────────────────────┘
```

The engine ([`introspect.py`](src/introspect_mcp/introspect.py)) is plain Python with
**zero dependencies beyond the MCP SDK**:

1. **Resolve** a dotted name by importing the longest importable module prefix, then
   walking the remaining attributes — so `os.path.join` and
   `collections.OrderedDict.move_to_end` both resolve correctly.
2. **Introspect** with the standard library: `inspect.signature`, `inspect.getdoc`,
   `inspect.getsource`, `inspect.getsourcefile`.
3. **Search** by walking a package's submodules one level deep (bounded + cached) and
   fuzzy-ranking with `difflib`.

Results are cached with `lru_cache`, so repeated lookups are instant.

---

## Honest limitations

No hand-wavy claims — here's exactly what it can and can't do:

- **Python only.** It introspects installed *Python* packages and your project's own
  Python code. Other languages are out of scope.
- **Resolving a name imports its module.** This is inherent to reading a live signature —
  there's no way around it in Python. Import side effects (rare in well-behaved libraries)
  will run. The server itself never writes or mutates anything; it's read-only by design.
- **C extensions have no Python source.** For things like `len` or parts of `numpy`'s
  core, `get_source` can't return code — it falls back to the docstring and says so.
- **It reflects what's installed, not what's "best."** That's the whole point: it tells the
  agent the truth about *your* environment, version warts and all.

---

## Why this exists

Built by [Hritik Datta](https://github.com/Hritikd). Most "AI hallucinates APIs" tooling
points the model at web docs. But the version on the web is rarely the version in your
venv — and your code shouldn't have to leave your machine to get an accurate answer. The
ground truth is already on disk. This just lets the agent read it.

If it saves you a debugging session, a ⭐ is appreciated — it's how others find it.

## Development

```bash
git clone https://github.com/Hritikd/introspect-mcp
cd introspect-mcp
uv venv && uv pip install -e ".[dev]"
pytest        # 25+ tests, all against the standard library (deterministic)
ruff check .
```

Contributions welcome — see [CONTRIBUTING.md](CONTRIBUTING.md).

## License

[MIT](LICENSE) © Hritik Datta
