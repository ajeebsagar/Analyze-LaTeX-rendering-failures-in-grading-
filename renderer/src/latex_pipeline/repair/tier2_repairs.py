"""Tier 2 repairs: heuristic, applied only when classifier confidence is high
enough OR corruption is detected. All idempotent.
"""
from __future__ import annotations

import re
from typing import List

from ..core import IRepairer, RepairOutcome
from ..classification.signals import MATH_COMMANDS


_ORPHAN_RAC = re.compile(r"(?<![A-Za-z\\])rac(\{[^{}]*\}\{[^{}]*\})")
_ORPHAN_EXT = re.compile(r"(?<![A-Za-z\\])ext(\{[^{}]*\})")
_ETA_ORPHAN_RE = re.compile(r"(?<![A-Za-z\\])(eta)\b")
_ALPHAETA_RE = re.compile(r"(?<![A-Za-z\\])alphaeta\b")
_GREEK_NAMES = sorted({"beta","gamma","theta","alpha","delta","phi","psi","omega","sigma","lambda"}, key=len, reverse=True)
_GREEK_NAME_RE = re.compile(r"(?<![A-Za-z\\])(" + "|".join(_GREEK_NAMES) + r")\b")
_MATH_ONLY_CHARSET = re.compile(r"^[\s\d+\-*/=<>(){}\[\].,;:|^_!?\\a-zA-Z]+$")
_SUP_SUB_ADJ = re.compile(r"[A-Za-z0-9}\)\]][\^_][A-Za-z0-9{(\-]")
# `\text{___...}` → `\text{\rule{Nem}{0.4pt}}` — fill-in-the-blank repair
_TEXT_UNDERSCORE_RUN = re.compile(r"\\text\{([^{}]*?)(_{3,})([^{}]*?)\}")
# `X}{Y}` extra-close-brace pattern that looks like a dropped \frac prefix.
# Capture two balanced denominator-shaped suffixes after a top-level `}`.
_MAYBE_LOST_FRAC = re.compile(r"^(?P<num>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\{(?P<den>[^{}]*(?:\{[^{}]*\}[^{}]*)*)\}\s*$")


class OrphanBackslashRepairer(IRepairer):
    """Recovers backslashes lost during JSON round-trips: \\beta -> eta, etc."""
    @property
    def name(self): return "orphan_backslash"
    @property
    def scope(self): return "math"

    def repair(self, text, *, classification=None, family_prior=0.0):
        applied: List[str] = []
        out = text

        # alphaeta -> \alpha\beta (compound)
        new = _ALPHAETA_RE.sub(r"\\alpha\\beta", out)
        if new != out: applied.append("repair_alphaeta"); out = new

        # eta -> \beta when surrounding context is math-shape
        def _eta_replace(m):
            start, end = m.span()
            ctx = out[max(0, start - 12): min(len(out), end + 12)]
            if re.search(r"\\[a-zA-Z]+|\\frac|\\alpha|\\gamma|[\\{}=^_]|[+\-=]", ctx):
                return "\\beta"
            return m.group(0)

        new = _ETA_ORPHAN_RE.sub(_eta_replace, out)
        if new != out: applied.append("repair_orphan_eta_to_beta"); out = new

        # other greek names
        def _greek_replace(m):
            start, end = m.span()
            ctx = out[max(0, start - 12): min(len(out), end + 12)]
            if re.search(r"\\[a-zA-Z]+|\\frac|[\\{}=^_]", ctx):
                return "\\" + m.group(1)
            return m.group(0)

        new = _GREEK_NAME_RE.sub(_greek_replace, out)
        if new != out: applied.append("repair_orphan_greek"); out = new

        # rac{a}{b} -> \frac{a}{b}
        new = _ORPHAN_RAC.sub(r"\\frac\1", out)
        if new != out: applied.append("repair_orphan_rac"); out = new

        # ext{...} -> \text{...}
        new = _ORPHAN_EXT.sub(r"\\text\1", out)
        if new != out: applied.append("repair_orphan_ext"); out = new

        return RepairOutcome(out, applied)


def _count_unescaped_dollars(s: str) -> int:
    n = i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            i += 2
            continue
        if s[i] == "$":
            n += 1
        i += 1
    return n


def _index_of_unescaped_dollar(s: str) -> int:
    i = 0
    while i < len(s):
        if s[i] == "\\" and i + 1 < len(s):
            i += 2
            continue
        if s[i] == "$":
            return i
        i += 1
    return -1


class MathOnlyWrapper(IRepairer):
    """Wraps a whole field in $...$ when the surrounding context strongly
    suggests math-only intent.

    Wrapping fires when ALL of these are true:
      - source family prior >= prior_threshold (e.g. rubric_criterion)
      - content has no `\\(` or `\\[` math delimiters
      - content has either zero unescaped `$`, OR exactly one orphan `$` at
        the very start / very end (handles truncation + missing-delimiter
        cases like `\\alpha + eta = -\\frac{1}{6}$`)
      - the un-wrapped candidate matches the math-only character class
      - the candidate contains at least one recognized math command, a
        sub/super adjacency, or escaped set-braces.
    """
    @property
    def name(self): return "wrap_math_only"
    @property
    def scope(self): return "global"

    def __init__(self, prior_threshold: float = 0.5):
        self._prior_threshold = prior_threshold

    def repair(self, text, *, classification=None, family_prior=0.0):
        if family_prior < self._prior_threshold:
            return RepairOutcome(text, [])

        s = text.strip()
        if not s:
            return RepairOutcome(text, [])

        # Refuse if other math delimiters are present.
        if "\\(" in s or "\\[" in s:
            return RepairOutcome(text, [])

        # Handle orphan-dollar truncation cases.
        n_dollars = _count_unescaped_dollars(s)
        candidate = s
        applied_name = self.name
        if n_dollars >= 2:
            # The user already opted into mixed math/prose. Don't touch.
            return RepairOutcome(text, [])
        if n_dollars == 1:
            idx = _index_of_unescaped_dollar(s)
            if idx == 0:
                candidate = s[1:].lstrip()
            elif idx == len(s) - 1:
                candidate = s[:-1].rstrip()
            else:
                # Orphan in the middle is ambiguous — leave alone.
                return RepairOutcome(text, [])
            applied_name = "wrap_math_only_strip_orphan_dollar"

        if not candidate:
            return RepairOutcome(text, [])
        if not _MATH_ONLY_CHARSET.match(candidate):
            return RepairOutcome(text, [])

        has_command = any(("\\" + cmd) in candidate for cmd in MATH_COMMANDS)
        has_supsub = bool(_SUP_SUB_ADJ.search(candidate))
        has_set_braces = bool(re.search(r"\\\{|\\\}", candidate))
        if not (has_command or has_supsub or has_set_braces):
            return RepairOutcome(text, [])

        lead = text[: len(text) - len(text.lstrip())]
        trail = text[len(text.rstrip()):]
        return RepairOutcome(lead + "$" + candidate + "$" + trail, [applied_name])


class FillBlankInTextRepairer(IRepairer):
    """Replace `\\text{___...}` underscore runs with a horizontal `\\rule`
    line, so KaTeX renders a blank line instead of crashing on a nested
    subscript chain."""

    @property
    def name(self): return "repair_fill_blank_in_text"
    @property
    def scope(self): return "math"

    def repair(self, text, *, classification=None, family_prior=0.0):
        applied: List[str] = []

        def _sub(m: re.Match) -> str:
            before, run, after = m.group(1), m.group(2), m.group(3)
            # 1em per underscore (capped at 6em) for visual proportionality.
            width = min(6, max(1, len(run)))
            return f"\\text{{{before}\\rule{{{width}em}}{{0.4pt}}{after}}}"

        new = _TEXT_UNDERSCORE_RUN.sub(_sub, text)
        if new != text:
            applied.append(self.name)
        return RepairOutcome(new, applied)


class MissingFracPrefixRepairer(IRepairer):
    """Detect `X}{Y}` patterns that suggest a dropped `\\frac{` prefix
    (common LLM/OCR corruption) and rewrite them as `\\frac{X}{Y}`.

    Conservative: only fires when the segment contains exactly one
    unbalanced closing brace AND the leftover structure unambiguously
    matches the fraction shape."""

    @property
    def name(self): return "repair_missing_frac_prefix"
    @property
    def scope(self): return "math"

    @staticmethod
    def _close_imbalance(s: str) -> int:
        """Return (#open - #close) counted depth-aware. Positive = unclosed
        opens. Negative = surplus closes."""
        depth = 0
        i = 0
        n = len(s)
        while i < n:
            c = s[i]
            if c == "\\" and i + 1 < n:
                i += 2; continue
            if c == "{":   depth += 1
            elif c == "}": depth -= 1
            i += 1
        return depth

    def repair(self, text, *, classification=None, family_prior=0.0):
        # Only attempt when there is exactly one surplus closing brace.
        if self._close_imbalance(text) >= 0:
            return RepairOutcome(text, [])
        # The pattern `X}{Y}` with X having no unmatched `{` and Y being
        # a balanced `{...}` group at the end.
        m = _MAYBE_LOST_FRAC.match(text.strip())
        if not m:
            return RepairOutcome(text, [])
        num, den = m.group("num"), m.group("den")
        # Require that num itself doesn't already contain a top-level `}`
        # (we want the rewrite to be unambiguous).
        if "}" in num.replace("\\}", "") and "{" not in num.replace("\\{", ""):
            return RepairOutcome(text, [])
        new = f"\\frac{{{num}}}{{{den}}}"
        # Round-trip check: the rewritten content must now be brace-balanced.
        if self._close_imbalance(new) != 0:
            return RepairOutcome(text, [])
        return RepairOutcome(new, [self.name])


def default_tier2_global() -> List[IRepairer]:
    return [MathOnlyWrapper()]


def default_tier2_math() -> List[IRepairer]:
    return [
        OrphanBackslashRepairer(),
        FillBlankInTextRepairer(),
        MissingFracPrefixRepairer(),
    ]
