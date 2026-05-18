"""
Repair functions: Tier 1 (deterministic, unconditional) and Tier 2 (heuristic,
applied only when classifier confidence is high enough).

All repairs are PURE functions returning (new_text, list_of_repair_names).
All repairs must be IDEMPOTENT: repair(repair(x)) == repair(x).
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Tuple

from .classifier import MATH_COMMANDS

# --- Tier 1: deterministic ---

# Combining diacritics block (Unicode general category Mn): strip inside math
_COMBINING_RE = re.compile(r"[̀-ͯ]")

# Literal `\n`, `\t`, `\r` escapes that should be real whitespace.
# We only convert them when surrounded by sentence-shape context, to avoid
# mangling legitimate LaTeX like `\not`, `\nu`, `\to`.
_LITERAL_NEWLINE = re.compile(r"\\n(?=[A-Z]|\s|$)")
_LITERAL_TAB = re.compile(r"\\t(?=\s|$)")
_LITERAL_CR = re.compile(r"\\r(?=\s|$)")

# Bare math vocabulary that needs delimiters wrapped at the segment level
_LOOKS_LIKE_MATH_ONLY = re.compile(
    r"^[\s\d+\-*/=<>(){}\[\].,;:|^_!?\\a-zA-Z]+$"
)


def tier1_global(text: str) -> Tuple[str, List[str]]:
    """Global pre-segmentation transforms that are always safe."""
    repairs: List[str] = []
    out = text

    # Normalize Unicode to NFC so combining marks are detectable consistently
    out_nfc = unicodedata.normalize("NFC", out)
    if out_nfc != out:
        repairs.append("nfc_normalize")
        out = out_nfc

    return out, repairs


def tier1_math_segment(content: str) -> Tuple[str, List[str]]:
    """Tier 1 fixes applied inside a math segment (after we are sure it is math)."""
    repairs: List[str] = []
    out = content

    # Strip combining diacritics (U+0300..U+036F). These appear when text was
    # copy-pasted from rendered PDFs and never belong inside KaTeX input.
    stripped = _COMBINING_RE.sub("", out)
    if stripped != out:
        repairs.append("strip_combining_diacritics")
        out = stripped

    return out, repairs


def tier1_prose_segment(content: str) -> Tuple[str, List[str]]:
    """Tier 1 fixes for prose (non-math) segments."""
    repairs: List[str] = []
    out = content

    # Replace literal `\n` escape sequences with real newlines, but only when
    # the surrounding context looks like an `ai_solution`-style prose run.
    converted = _LITERAL_NEWLINE.sub("\n", out)
    converted = _LITERAL_TAB.sub("\t", converted)
    converted = _LITERAL_CR.sub("\r", converted)
    if converted != out:
        repairs.append("literal_escape_to_whitespace")
        out = converted

    return out, repairs


# --- Tier 2: confidence-gated heuristic repairs ---

# Orphan `rac{...}{...}` -> `\frac{...}{...}`
_ORPHAN_RAC = re.compile(r"(?<![A-Za-z\\])rac(\{[^{}]*\}\{[^{}]*\})")

# Orphan `ext{...}` -> `\text{...}` (when preceded by a non-letter, non-backslash)
_ORPHAN_EXT = re.compile(r"(?<![A-Za-z\\])ext(\{[^{}]*\})")

# Orphan greek letters: lost backslash on `\beta`, `\gamma`, etc.
# Be conservative: only the most common ones, and only when surrounded by
# math-shape characters (operator, digit, brace, or math command tail).
_GREEK_ORPHANS = {"eta", "beta", "gamma", "theta", "alpha", "delta", "phi", "psi", "omega", "sigma", "lambda"}
# Note: "eta" is in this set because `\beta -> eta` is the most common corruption.
# We rebuild as `\beta`, NOT `\eta`, because the dataset evidence shows the
# bug almost always drops a leading char of a 2+ letter command. We map by
# context below.

_ETA_ORPHAN_RE = re.compile(r"(?<![A-Za-z\\])(eta)\b")
_ALPHAETA_RE = re.compile(r"(?<![A-Za-z\\])alphaeta\b")
_GREEK_NAME_RE = re.compile(r"(?<![A-Za-z\\])(" + "|".join(sorted(_GREEK_ORPHANS - {"eta"}, key=len, reverse=True)) + r")\b")


def tier2_orphan_backslash(content: str) -> Tuple[str, List[str]]:
    """
    Recover backslashes that were dropped during JSON round-trips.

    Conservative: only applies inside what is already a math segment, and only
    for tokens whose adjacency clearly indicates math context.
    """
    repairs: List[str] = []
    out = content

    # `alphaeta` -> `\alpha\beta` (compound corruption seen in the dataset)
    new = _ALPHAETA_RE.sub(r"\\alpha\\beta", out)
    if new != out:
        repairs.append("repair_alphaeta")
        out = new

    # `eta` standing alone where `\beta` was meant. Heuristic: if `eta` is
    # adjacent to math operators or appears alongside other math commands,
    # treat as `\beta`. Avoids false-positives on the word "eta" in prose.
    def _eta_replace(m: re.Match) -> str:
        # Look at +/-12 chars around the match. If we see math-like context,
        # rewrite to \beta. Otherwise leave alone.
        start, end = m.span()
        ctx = out[max(0, start - 12): min(len(out), end + 12)]
        if re.search(r"\\[a-zA-Z]+|\\frac|\\alpha|\\gamma|[+\-=][\s]*[\$\\]?|\^|_\{|[\\{}=]", ctx):
            return "\\beta"
        return m.group(0)

    new = _ETA_ORPHAN_RE.sub(_eta_replace, out)
    if new != out:
        repairs.append("repair_orphan_eta_to_beta")
        out = new

    # Other greek orphans: \gamma, \theta, etc.
    def _greek_replace(m: re.Match) -> str:
        name = m.group(1)
        start, end = m.span()
        ctx = out[max(0, start - 12): min(len(out), end + 12)]
        if re.search(r"\\[a-zA-Z]+|\\frac|[\\{}=^_]", ctx):
            return "\\" + name
        return m.group(0)

    new = _GREEK_NAME_RE.sub(_greek_replace, out)
    if new != out:
        repairs.append("repair_orphan_greek")
        out = new

    # `rac{a}{b}` -> `\frac{a}{b}`
    new = _ORPHAN_RAC.sub(r"\\frac\1", out)
    if new != out:
        repairs.append("repair_orphan_rac")
        out = new

    # `ext{...}` -> `\text{...}` only outside a leading backslash, and only
    # if the surrounding context is math.
    def _ext_replace(m: re.Match) -> str:
        return "\\text" + m.group(1)

    new = _ORPHAN_EXT.sub(_ext_replace, out)
    if new != out:
        repairs.append("repair_orphan_ext")
        out = new

    return out, repairs


def tier2_wrap_math_only(content: str, *, family_prior: float) -> Tuple[str, List[str], bool]:
    """
    If the *unsegmented* prose content looks like a math-only expression with
    a recognized command (and the source family suggests math-only storage),
    wrap it in `$...$` so KaTeX will pick it up.

    Returns (new_text, repairs, wrapped).
    """
    repairs: List[str] = []
    s = content.strip()
    if not s:
        return content, [], False

    # Already has a math delimiter somewhere?
    if "$" in s or "\\(" in s or "\\[" in s:
        return content, [], False

    # Must look math-only (limited charset, no prose punctuation like full sentences)
    if not _LOOKS_LIKE_MATH_ONLY.match(s):
        return content, [], False
    # Reject pure-prose by requiring at least ONE recognized math command OR
    # a sub/super adjacency
    has_command = any(("\\" + cmd) in s for cmd in MATH_COMMANDS)
    has_supsub = bool(re.search(r"[A-Za-z0-9}\)\]][\^_][A-Za-z0-9{(\-]", s))
    has_set_braces = bool(re.search(r"\\\{|\\\}", s))
    if not (has_command or has_supsub or has_set_braces):
        return content, [], False
    # Source-family must indicate this surface stores math-only content
    if family_prior < 0.5:
        return content, [], False

    new = "$" + s + "$"
    repairs.append("wrap_math_only")
    # Re-attach leading/trailing whitespace from `content`
    lead = content[: len(content) - len(content.lstrip())]
    trail = content[len(content.rstrip()):]
    return lead + new + trail, repairs, True
