"""StateMachineSegmenter — recognizes $..$, $$..$$, \\(..\\), \\[..\\].

Single Responsibility: turn a string into a list of Segment objects.
No classification, no repair, no rendering.
"""
from __future__ import annotations

from typing import List

from ..core import ISegmenter, Segment, SegmentKind


class StateMachineSegmenter(ISegmenter):
    """Default segmenter. Stateless, thread-safe."""

    def segment(self, text: str) -> List[Segment]:
        raw = self._segment_raw(text)
        # Post-process: coalesce empty math segments back into text. These are
        # `$$` / `$ $` / `\(\)` / `\[\]` patterns that arise from truncated
        # AI-solution prose and would otherwise produce a fallback span.
        return self._coalesce_empty_math(text, raw)

    @staticmethod
    def _coalesce_empty_math(text: str, segs: List[Segment]) -> List[Segment]:
        if not segs:
            return segs
        out: List[Segment] = []
        for s in segs:
            if s.kind != SegmentKind.TEXT and not s.content.strip():
                # Empty math — convert to literal text containing the original
                # delimiters as they appeared in the source.
                literal = text[s.start:s.end]
                if out and out[-1].kind == SegmentKind.TEXT:
                    # Merge with previous text segment for cleaner output.
                    prev = out[-1]
                    out[-1] = Segment(SegmentKind.TEXT, prev.content + literal,
                                      prev.start, s.end)
                else:
                    out.append(Segment(SegmentKind.TEXT, literal, s.start, s.end))
            else:
                if out and out[-1].kind == SegmentKind.TEXT and s.kind == SegmentKind.TEXT:
                    prev = out[-1]
                    out[-1] = Segment(SegmentKind.TEXT, prev.content + s.content,
                                      prev.start, s.end)
                else:
                    out.append(s)
        return out

    def _segment_raw(self, text: str) -> List[Segment]:
        if not text:
            return []

        # Truncation guard: if unescaped-dollar count is odd, treat the trailing
        # orphan `$` as literal text so we never open math that cannot close.
        total_dollars = self._count_unescaped_dollars(text)
        odd_dollar = (total_dollars % 2 == 1)

        out: List[Segment] = []
        buf_start = 0
        i = 0
        n = len(text)
        seen_dollars = 0

        def flush_text(upto: int) -> None:
            if upto > buf_start:
                out.append(Segment(SegmentKind.TEXT, text[buf_start:upto], buf_start, upto))

        while i < n:
            c = text[i]

            # Escaped dollar -> literal text
            if c == "\\" and i + 1 < n and text[i + 1] == "$":
                i += 2
                continue

            # \(...\) or \[...\]
            if c == "\\" and i + 1 < n and text[i + 1] in "([":
                opener = text[i:i + 2]
                close = {"\\(": "\\)", "\\[": "\\]"}[opener]
                j = text.find(close, i + 2)
                if j == -1:
                    i += 2
                    continue
                flush_text(i)
                kind = SegmentKind.MATH_PAREN if opener == "\\(" else SegmentKind.MATH_BRACKET
                out.append(Segment(kind, text[i + 2:j], i, j + 2))
                i = j + 2
                buf_start = i
                continue

            # $$...$$
            if c == "$" and i + 1 < n and text[i + 1] == "$":
                j = text.find("$$", i + 2)
                if j == -1:
                    i += 2
                    continue
                flush_text(i)
                out.append(Segment(SegmentKind.MATH_DISPLAY, text[i + 2:j], i, j + 2))
                seen_dollars += 2
                i = j + 2
                buf_start = i
                continue

            # $...$
            if c == "$":
                seen_dollars += 1
                if odd_dollar and seen_dollars == total_dollars:
                    # Skip the orphan trailing `$` — treat as literal text.
                    i += 1
                    continue
                j = self._find_unescaped_dollar(text, i + 1)
                if j == -1:
                    i += 1
                    continue
                flush_text(i)
                out.append(Segment(SegmentKind.MATH_INLINE, text[i + 1:j], i, j + 1))
                seen_dollars += 1
                i = j + 1
                buf_start = i
                continue

            i += 1

        flush_text(n)
        return out

    @staticmethod
    def _count_unescaped_dollars(text: str) -> int:
        n = 0
        i = 0
        while i < len(text):
            c = text[i]
            if c == "\\" and i + 1 < len(text):
                i += 2
                continue
            if c == "$":
                n += 1
            i += 1
        return n

    @staticmethod
    def _find_unescaped_dollar(text: str, start: int) -> int:
        i = start
        n = len(text)
        while i < n:
            c = text[i]
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "$":
                return i
            i += 1
        return -1
