# Installation

The implementation is still taking shape, so there is not yet an installable package or runtime distribution to consume.

For now, the repository provides the project description and documentation pipeline. Once code is published, this page will document installation options, supported environments, and version compatibility.

## Documentation tooling

To build the docs locally:

```bash
uv sync --group docs
uv run mkdocs serve
```