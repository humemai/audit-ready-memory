# The hosted demo. The library itself needs no container: `uv add audit-ready-memory`.
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    SETUPTOOLS_SCM_PRETEND_VERSION=0.1.0.dev0

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY audit_ready_memory ./audit_ready_memory
RUN uv sync --locked --no-dev --extra demo

COPY demo ./demo
COPY docs/brand/export ./docs/brand/export
COPY .streamlit/config.toml ./.streamlit/config.toml

# demo/start.py starts as root only to take ownership of the mounted disk, then drops to this user.
RUN useradd --uid 10001 --create-home app && chown -R app:app /app/.streamlit

ENV ARM_DEMO_DATA=/data
EXPOSE 8501
CMD ["/app/.venv/bin/python", "demo/start.py"]
