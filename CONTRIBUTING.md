# Contributing

Thanks for considering a contribution! This project is intentionally small and
dependency-light — please keep it that way.

## Setup

```bash
git clone https://github.com/Hritikd/introspect-mcp
cd introspect-mcp
uv venv && uv pip install -e ".[dev]"
```

## Before opening a PR

```bash
pytest        # all tests must pass
ruff check .  # must be clean
```

Tests target the **standard library** so they run deterministically anywhere — please
follow that pattern rather than adding third-party packages as test fixtures.

## Good first issues

- Add a `get_type_hints` tool (resolved annotations via `typing.get_type_hints`).
- Support listing a class's full MRO and where each method is defined.
- A `diff_signature(name, expected)` tool that flags drift between what an agent
  expects and what's installed.

## Principles

- **Read-only.** No tool may write, mutate, or execute beyond import side effects.
- **Zero runtime deps** beyond the MCP SDK.
- **Honesty in docs.** No inflated claims — describe exactly what it does.
