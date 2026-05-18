"""
Plain-text fallback: HTML-escape content so it never re-enters the parser.
The fallback renderer is intentionally trivial and exception-free.
"""
from __future__ import annotations

_ESCAPE_MAP = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
}


def html_escape(s: str) -> str:
    return "".join(_ESCAPE_MAP.get(c, c) for c in s)


def fallback_span(content: str, *, reason: str) -> str:
    """Render a failed segment as escaped text inside a labeled span.

    The data-render-reason attribute is for telemetry only.
    """
    return (
        f'<span class="latex-fallback" data-render-reason="{html_escape(reason)}">'
        f'{html_escape(content)}</span>'
    )
