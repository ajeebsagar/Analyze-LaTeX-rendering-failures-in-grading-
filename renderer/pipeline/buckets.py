"""
Bucket labeller — maps the per-segment signals to the named failure buckets
from the production architecture spec.

Buckets:
  A — missing_delimiters
  B — broken_braces
  C — unbalanced_dollar
  D — ocr_corruption
  E — invalid_command_name
  F — unsupported_environment
  G — mixed_prose_math
  H — false_positive
  I — code_snippet
  J — currency_text
  K — nested_parser_corruption
  L — multiline_ai_solution
  Z — clean (no failure)
"""
from __future__ import annotations

import re
from typing import List

from .classifier import ClassificationResult
from .renderer import PipelineResult, SegmentResult


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
_RE_HTML_TABLE = re.compile(r"<(table|thead|tbody|tr|td|th)\b", re.I)
_RE_BACKSLASH_N = re.compile(r"\\n[^a-zA-Z]")
_RE_LITERAL_CURRENCY = re.compile(r"^\s*\$\s*\d+(?:[,.]\d+)?\s*[A-Za-z]{0,15}\s*$")


def label_buckets(text: str, result: PipelineResult) -> List[str]:
    """
    Return the set of bucket labels that fired for this row.
    Multiple buckets can apply to a single input.
    """
    hits = set()

    # Signal-based labels per segment
    for sr in result.segments:
        sig = sr.classification.signals if sr.classification else {}
        if sr.classification.is_html:
            hits.add("F")  # treat HTML as "unsupported environment" at the math layer
        if sr.classification.is_currency:
            hits.add("J")
        if sr.classification.is_fill_blank:
            hits.add("H")
        if sr.classification.corruption:
            hits.add("D")
        # OCR/corruption signals
        corr = sig.get("corruption") or []
        if any(c in {"eta", "rac", "ext", "alphaeta"} for c in corr):
            hits.add("D")
        # Validation-based labels
        for reason in sr.validation_reasons:
            if reason.startswith("forbidden_command"):
                hits.add("E")
            elif "brace" in reason:
                hits.add("B")
            elif reason == "subscript_run_too_long":
                hits.add("H")
            elif reason == "html_content":
                hits.add("F")

    # Whole-text labels — repairs applied tell us what was broken pre-repair
    repairs = set(result.repairs_applied or [])
    if "wrap_math_only" in repairs:
        hits.add("A")  # missing delimiters was the root condition
    if any(r in repairs for r in (
        "repair_orphan_eta_to_beta", "repair_orphan_rac", "repair_orphan_ext",
        "repair_alphaeta", "repair_orphan_greek", "strip_combining_diacritics",
    )):
        hits.add("D")  # OCR / JSON round-trip corruption (backslashes lost, diacritics)
    if "literal_escape_to_whitespace" in repairs:
        hits.add("L")  # multiline ai_solution with literal \n
    if _RE_CODE_FENCE.search(text):
        hits.add("I")
    if _RE_HTML_TABLE.search(text):
        hits.add("F")
    if _RE_BACKSLASH_N.search(text):
        hits.add("L")
    if _RE_LITERAL_CURRENCY.match(text):
        hits.add("J")

    # Mixed prose + math: at least one math segment AND at least one non-empty text segment
    n_math = sum(1 for s in result.segments if s.rendered_as == "math")
    n_text = sum(1 for s in result.segments if s.rendered_as == "text" and s.original.strip())
    if n_math >= 1 and n_text >= 1:
        hits.add("G")

    # Truncation -> unbalanced dollar bucket
    # Detect via failure_reasons or odd-dollar removed-by-segmenter
    if any("dollar" in r for r in result.failure_reasons):
        hits.add("C")

    # Nested parser corruption: text-in-math nesting
    for sr in result.segments:
        if sr.is_math if hasattr(sr, "is_math") else sr.rendered_as == "math":
            content = sr.repaired
            if "\\text{" in content and ("\\sqrt" in content or "\\frac" in content):
                # \text{...} that contains math commands suggests nested mode conflict
                if re.search(r"\\text\{[^}]*\\(sqrt|frac|alpha|beta)", content):
                    hits.add("K")

    if not hits:
        hits.add("Z")

    return sorted(hits)
