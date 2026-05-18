"""HTML-escaping fallback renderer. Never throws, never re-parses."""
from __future__ import annotations

from ..core import IFallbackRenderer

_ESCAPE = {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}


def html_escape(s: str) -> str:
    return "".join(_ESCAPE.get(c, c) for c in s)


class HtmlFallbackRenderer(IFallbackRenderer):
    """Emits a <span class="latex-fallback"> with escaped content and a
    machine-readable reason attribute for telemetry."""

    def __init__(self, css_class: str = "latex-fallback"):
        self._css_class = css_class

    def render(self, content: str, *, reason: str) -> str:
        return (f'<span class="{self._css_class}" data-render-reason="'
                f'{html_escape(reason)}">{html_escape(content)}</span>')
