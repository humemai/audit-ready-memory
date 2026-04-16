# Documentation

This project uses MkDocs Material and versioned publishing with `mike`.

## Local build

```bash
uv sync --group docs
uv run mkdocs build --strict
```

## Local preview

```bash
uv run mkdocs serve
```

## Deployment model

Published documentation is deployed into the shared `humemai-docs` repository under the `audit-ready-memory/` prefix.

This keeps the public docs hosted side by side with other HumemAI documentation sets while leaving source ownership in this repository.