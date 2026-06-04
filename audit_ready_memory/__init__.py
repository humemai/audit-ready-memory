"""Audit-ready, local-first memory for AI agents."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("audit-ready-memory")
except PackageNotFoundError:
    __version__ = "0+unknown"
