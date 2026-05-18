"""Maps PipelineResult to one or more bucket labels (A-L, Z).

SRP: ONLY classifies failure shape. Adding a bucket = adding a rule entry.
"""
from __future__ import annotations

import re
from typing import List

from ..core import IBucketLabeler, PipelineResult, RenderOutcome


BUCKET_DESCRIPTIONS = {
    "A": "missing_delimiters",
    "B": "broken_braces",
    "C": "unbalanced_dollar",
    "D": "ocr_corruption",
    "E": "invalid_command_name",
    "F": "unsupported_environment",
    "G": "mixed_prose_math",
    "H": "false_positive",
    "I": "code_snippet",
    "J": "currency_text",
    "K": "nested_parser_corruption",
    "L": "multiline_ai_solution",
    "Z": "clean",
}


_RE_CODE_FENCE = re.compile(r"```|<pre>|<code>", re.I)
_RE_INLINE_BACKTICK = re.compile(r"`[^`\n]+`")
_RE_HTML_TABLE = re.compile(r"<(table|thead|tbody|tr|td|th)\b", re.I)
_RE_BACKSLASH_N_IN_PROSE = re.compile(r"\\n[^a-zA-Z]")
_RE_LITERAL_CURRENCY = re.compile(r"^\s*\$\s*\d+(?:[,.]\d+)?\s*[A-Za-z]{0,15}\s*$")
# Currency-in-prose: $<digits> embedded in a prose sentence (multiple $-amounts allowed)
_RE_PROSE_CURRENCY = re.compile(r"\$\s*\d+(?:[,.]\d+)?(?:\s*(?:[A-Z]{2,4}|per|each|/|month|year|kg|lb|hour|day|week)\b)?", re.I)

_REPAIR_TO_BUCKET = {
    "wrap_math_only": "A",
    "wrap_math_only_strip_orphan_dollar": "A",  # bucket A + bucket C combo
    "repair_orphan_eta_to_beta": "D",
    "repair_orphan_rac": "D",
    "repair_orphan_ext": "D",
    "repair_alphaeta": "D",
    "repair_orphan_greek": "D",
    "strip_combining_diacritics": "D",
    "literal_escape_to_whitespace": "L",
}


class BucketLabeler(IBucketLabeler):
    """Default labeler. Easy to extend by injecting custom rule maps."""

    def __init__(self, repair_to_bucket: dict[str, str] | None = None):
        self._repair_to_bucket = dict(_REPAIR_TO_BUCKET)
        if repair_to_bucket:
            self._repair_to_bucket.update(repair_to_bucket)

    def label(self, original_text: str, result: PipelineResult) -> List[str]:
        hits: set[str] = set()

        # 1. Repair-applied implies which bucket fired pre-repair
        for r in result.repairs_applied or ():
            b = self._repair_to_bucket.get(r)
            if b:
                hits.add(b)

        # 2. Per-segment signals
        for sr in result.segments:
            cls = sr.classification
            if cls.is_html: hits.add("F")
            if cls.is_currency: hits.add("J")
            if cls.is_fill_blank: hits.add("H")
            if cls.has_corruption: hits.add("D")

            for reason in sr.validation.reasons:
                if reason.startswith("forbidden_command"):
                    hits.add("E")
                elif "brace" in reason:
                    hits.add("B")
                elif reason == "subscript_run_too_long":
                    hits.add("H")

            if sr.outcome is RenderOutcome.MATH:
                # Nested parser corruption: \text{...} containing math commands
                if re.search(r"\\text\{[^}]*\\(sqrt|frac|alpha|beta|gamma)", sr.repaired):
                    hits.add("K")

        # 3. Whole-text shape hints
        if _RE_CODE_FENCE.search(original_text) or _RE_INLINE_BACKTICK.search(original_text):
            hits.add("I")
        if _RE_HTML_TABLE.search(original_text):
            hits.add("F")
        if _RE_BACKSLASH_N_IN_PROSE.search(original_text):
            hits.add("L")
        if _RE_LITERAL_CURRENCY.match(original_text):
            hits.add("J")
        # Currency in prose: $<digits> patterns embedded in prose. Only fires
        # when no math segments rendered (pure-text outcome) to avoid tagging
        # real math like $5x + 3$.
        n_math_segments = sum(1 for s in result.segments if s.outcome is RenderOutcome.MATH)
        if n_math_segments == 0 and _RE_PROSE_CURRENCY.search(original_text):
            hits.add("J")

        # 4. Mixed prose + math
        n_math = sum(1 for s in result.segments if s.outcome is RenderOutcome.MATH)
        n_text = sum(1 for s in result.segments
                     if s.outcome is RenderOutcome.TEXT and s.original.strip())
        if n_math >= 1 and n_text >= 1:
            hits.add("G")

        # 5. Truncated/unbalanced dollar — segmenter dropped an orphan
        unescaped_dollars = self._count_unescaped_dollars(original_text)
        if unescaped_dollars % 2 == 1:
            hits.add("C")

        if not hits:
            hits.add("Z")

        return sorted(hits)

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
