"""
State-machine tokenizer for mixed prose + LaTeX text.

Recognizes four math-delimiter styles:
  - inline:  $...$
  - display: $$...$$
  - paren:   \\(...\\)
  - bracket: \\[...\\]

Honors escaped dollar (`\\$`) as literal text and does not enter math mode.
If the count of unescaped `$` is odd, the last opener is treated as literal
(truncation guard).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Segment:
    kind: str       # 'text' | 'math_inline' | 'math_display' | 'math_paren' | 'math_bracket' | 'html'
    content: str    # raw inside-delimiter content for math; raw chars for text/html
    start: int      # offset in the original string (inclusive)
    end: int        # offset in the original string (exclusive)

    @property
    def is_math(self) -> bool:
        return self.kind.startswith("math_")


def _count_unescaped_dollars(s: str) -> int:
    """Count `$` characters not preceded by a single backslash."""
    n = 0
    i = 0
    while i < len(s):
        c = s[i]
        if c == "\\" and i + 1 < len(s):
            i += 2
            continue
        if c == "$":
            n += 1
        i += 1
    return n


def segment(text: str) -> List[Segment]:
    """
    Split `text` into a list of Segment objects.

    Math openers are scanned in priority order at each cursor position:
      `$$`, `\\(`, `\\[`, `$`.
    `\\$` is consumed as a two-character literal and does NOT open math.
    """
    if not text:
        return []

    # Truncation guard: if unescaped-dollar count is odd, drop the last `$`
    # opener so it is rendered as literal text. This produces no math segment
    # for a clearly truncated formula like "... $V = q/r" and keeps the
    # surrounding prose intact.
    odd_dollar = _count_unescaped_dollars(text) % 2 == 1

    out: List[Segment] = []
    buf_start = 0
    i = 0
    n = len(text)

    # Track how many unescaped `$` we have already consumed so we can ignore
    # the trailing orphan when the total count is odd.
    seen_dollars = 0
    total_dollars = _count_unescaped_dollars(text) if odd_dollar else 0

    def flush_text(upto: int) -> None:
        if upto > buf_start:
            out.append(Segment("text", text[buf_start:upto], buf_start, upto))

    while i < n:
        c = text[i]

        # Escaped dollar -> literal
        if c == "\\" and i + 1 < n and text[i + 1] == "$":
            i += 2
            continue

        # Backslash escape for non-dollar -> consume two chars as text
        if c == "\\" and i + 1 < n and text[i + 1] in "()[]":
            opener = text[i : i + 2]
            close = {"\\(": "\\)", "\\[": "\\]"}.get(opener)
            if close is None:
                i += 2
                continue
            # find matching closer
            j = text.find(close, i + 2)
            if j == -1:
                # unclosed; treat opener as literal text
                i += 2
                continue
            flush_text(i)
            kind = "math_paren" if opener == "\\(" else "math_bracket"
            out.append(Segment(kind, text[i + 2 : j], i, j + 2))
            i = j + 2
            buf_start = i
            continue

        # $$...$$
        if c == "$" and i + 1 < n and text[i + 1] == "$":
            j = text.find("$$", i + 2)
            if j == -1:
                # unclosed display delim; treat as literal
                i += 2
                continue
            flush_text(i)
            out.append(Segment("math_display", text[i + 2 : j], i, j + 2))
            seen_dollars += 2  # opener and closer
            i = j + 2
            buf_start = i
            continue

        # $...$
        if c == "$":
            seen_dollars += 1
            # If this is the orphan trailing `$` from a truncated input,
            # treat it as literal text and stop scanning for math.
            if odd_dollar and seen_dollars == total_dollars:
                i += 1
                continue
            # Find next unescaped `$`
            j = _find_unescaped_dollar(text, i + 1)
            if j == -1:
                # No closing `$`; treat opener as literal text.
                i += 1
                continue
            flush_text(i)
            out.append(Segment("math_inline", text[i + 1 : j], i, j + 1))
            seen_dollars += 1
            i = j + 1
            buf_start = i
            continue

        i += 1

    flush_text(n)
    return out


def _find_unescaped_dollar(text: str, start: int) -> int:
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "$":
            # Treat `$$` inside an inline segment as still a closing-then-opening
            # rather than ending current segment, by deferring to caller.
            return i
        i += 1
    return -1
