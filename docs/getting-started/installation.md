# Installation

Python 3.10 or newer. The database is embedded, so there is nothing to install or run beside
the package itself.

## From PyPI

```bash
uv add audit-ready-memory
```

Check it worked:

```bash
uv run python -c "from audit_ready_memory import Memory; print('ok')"
```

Versions are below `0.1.0` on purpose: the API is usable but not frozen. Pin an exact version
if you depend on it.

## Without installing anything

To try it in a throwaway environment that leaves nothing behind:

```bash
uv run --with audit-ready-memory python
```

## From source

For the demo, the tests, or to work on the library itself:

```bash
git clone https://github.com/humemai/audit-ready-memory
cd audit-ready-memory
uv sync
```

## Optional extras

The demo needs Streamlit and the file parsers:

```bash
uv sync --extra demo
```

Everything, including test and documentation tooling:

```bash
uv sync --all-groups --all-extras
```

## Dependencies

Two at runtime:

- `arcadedb-embedded` for the local database. It bundles a JVM, so the wheel is large, around
  63 MB. There is no server component.
- `pydantic` for the event schema.

The `demo` extra adds `streamlit`, `openai`, `pandas`, `openpyxl`, `pypdf`, and
`python-dotenv`.

## Running the tests

```bash
uv run pytest
```

## Configuration

The library itself needs no configuration. The demo reads `OPENROUTER_API_KEY` from the
environment or a `.env` file, and runs without it with the AI chat disabled. Copy
`.env.example` to `.env` to set one. The key is never written to the memory database or the
log.

## Where data goes

`Memory("./memory-db")` creates and uses that directory. It is the whole database: back it
up, move it, or delete it as a unit. Restrict its permissions to the service user, because
content is stored unencrypted.

## Building the docs

```bash
uv sync --group docs
uv run mkdocs serve
```
