"""Shared LangSmith tracing decorator.

`traceable` wraps a function as a named span in the LangSmith trace tree, so the
pipeline renders as readable steps (each agent, each per-candidate operation)
with their inputs and outputs. Falls back to a no-op when langsmith is absent,
so the app runs identically without tracing configured.
"""

from __future__ import annotations

try:
    from langsmith import traceable
except Exception:  # pragma: no cover
    def traceable(*d_args, **d_kwargs):
        def _wrap(fn):
            return fn
        return _wrap(d_args[0]) if d_args and callable(d_args[0]) else _wrap
