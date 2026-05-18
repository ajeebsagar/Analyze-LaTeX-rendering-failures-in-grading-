"""
Pre-parse validation. We catch the easy-to-detect failure shapes BEFORE
invoking KaTeX, so we can route to fallback without paying a parse exception.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List

# Hard limits. Tuned to corpus: longest legitimate `ai_solution` is ~6KB.
MAX_LENGTH = 8000
MAX_BRACE_DEPTH = 32
MAX_SUB_DEPTH = 6   # `__________` typically blows past this

# Security: commands that should never be invoked from user content. KaTeX
# already restricts most of these via `trust: false`, but we double-check.
FORBIDDEN_COMMANDS = {
    "input", "include", "write", "openout", "closeout", "immediate",
    "csname", "endcsname", "loop", "repeat", "newif",
    "href", "url", "includegraphics",  # only safe if we explicitly allow
}

_RE_COMMAND = re.compile(r"\\([a-zA-Z]+)")
_RE_SUB_RUN = re.compile(r"_{3,}")


@dataclass
class ValidationResult:
    ok: bool
    reasons: List[str]  # empty if ok=True


def validate(math_content: str) -> ValidationResult:
    reasons: List[str] = []

    if not math_content or not math_content.strip():
        return ValidationResult(False, ["empty_math_segment"])

    if len(math_content) > MAX_LENGTH:
        reasons.append("exceeds_max_length")

    # Brace balance + depth
    depth = 0
    max_depth = 0
    i = 0
    n = len(math_content)
    while i < n:
        c = math_content[i]
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c == "{":
            depth += 1
            if depth > max_depth:
                max_depth = depth
        elif c == "}":
            depth -= 1
            if depth < 0:
                reasons.append("unbalanced_close_brace")
                break
        i += 1
    if depth != 0 and "unbalanced_close_brace" not in reasons:
        reasons.append("unbalanced_brace_count")
    if max_depth > MAX_BRACE_DEPTH:
        reasons.append("brace_depth_exceeded")

    # Fill-in-the-blank `_{3,}` -> subscript chain depth
    if _RE_SUB_RUN.search(math_content):
        reasons.append("subscript_run_too_long")

    # Forbidden commands
    for m in _RE_COMMAND.finditer(math_content):
        if m.group(1) in FORBIDDEN_COMMANDS:
            reasons.append(f"forbidden_command:{m.group(1)}")
            break

    return ValidationResult(ok=not reasons, reasons=reasons)
