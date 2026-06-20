# Wiring introspect-mcp into Claude Code

## Option A — one-liner (uses uvx)

```bash
claude mcp add introspect -- uvx introspect-mcp
```

Run from this repo until it's on PyPI:

```bash
claude mcp add introspect -- uvx --from git+https://github.com/Hritikd/introspect-mcp introspect-mcp
```

## Option B — pin to your project's venv (recommended)

So the server sees *your* installed dependencies, point it at your project interpreter.
Add to `.mcp.json` at your project root:

```json
{
  "mcpServers": {
    "introspect": {
      "command": "${workspaceFolder}/.venv/bin/python",
      "args": ["-m", "introspect_mcp"]
    }
  }
}
```

(Install it there first: `uv pip install introspect-mcp` inside that venv.)

## Try it

Ask Claude Code:

> "Use the introspect tools to show me the real signature of `requests.Session.request`
> in this project, then write a wrapper around it."
