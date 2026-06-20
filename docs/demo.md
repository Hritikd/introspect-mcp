# Walkthrough

An illustrative session showing how an agent uses `introspect-mcp` to avoid a
version-mismatch bug. Tool outputs below are the **real** format the server returns
(verified against the standard library).

---

### 1. The agent half-remembers a name

> **User:** read `data.csv` into a dataframe and keep only rows where `amount > 100`.

```text
agent → search_symbols(query="read csv", package="pandas")
```
```json
{
  "query": "read csv",
  "package": "pandas",
  "count": 3,
  "results": [
    { "name": "pandas.read_csv", "score": 1.0 },
    { "name": "pandas.io.parsers.read_csv", "score": 1.0 },
    { "name": "pandas.read_excel", "score": 0.62 }
  ]
}
```

### 2. It confirms the exact signature before calling

```text
agent → get_signature("pandas.read_csv")
```
```text
read_csv(filepath_or_buffer, *, sep=<no_default>, delimiter=None, header='infer', ...)
```

### 3. It avoids a removed method

```text
agent → lookup_symbol("pandas.DataFrame.append")
```
```json
{
  "error": "'pandas.DataFrame' has no attribute 'append' (installed version may differ from what you expected.)",
  "type": "ResolveError"
}
```

The agent now *knows* `.append()` is gone in pandas 2.x — instead of generating code
that crashes at runtime — and reaches for `pd.concat`.

---

### What the standard-library version looks like (reproducible)

You can reproduce these exactly with no third-party installs:

```text
get_signature("json.dumps")
→ dumps(obj, *, skipkeys=False, ensure_ascii=True, check_circular=True, allow_nan=True,
        cls=None, indent=None, separators=None, default=None, sort_keys=False, **kw)
```

```text
lookup_symbol("pathlib.Path.glob")
→ {
    "name": "pathlib.Path.glob",
    "kind": "function",
    "signature": "(self, pattern, *, case_sensitive=None)",
    "summary": "Iterate over this subtree and yield all existing files ...",
    "location": ".../pathlib.py:1056"
  }
```

The signature is whatever is installed on *your* machine — that's the entire point.
