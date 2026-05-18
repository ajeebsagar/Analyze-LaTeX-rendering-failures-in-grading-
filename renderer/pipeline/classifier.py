"""
Confidence-based math-intent classifier.

Given a string segment (and optional source-family hint), produce a score in
[0,1] expressing how confident we are that the content should be rendered as
math. Score is built from additive signals:

  + recognized LaTeX commands  (\\frac, \\sqrt, \\alpha, ...)
  + sub/superscript adjacency  (x^2, H_2O)
  + math operators in dense ratio
  - corruption signals         (orphan `eta`, `rac{`, `ext{`)
  - currency shape             ($5 cake, $10 - 4)
  - pure-alpha short token     ($apple$)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

# Recognized command vocabulary (subset that covers >99% of the dataset)
MATH_COMMANDS = {
    "frac", "sqrt", "alpha", "beta", "gamma", "delta", "epsilon", "theta",
    "lambda", "mu", "nu", "pi", "rho", "sigma", "tau", "phi", "chi", "psi",
    "omega", "varepsilon", "vartheta", "varphi", "Delta", "Sigma", "Omega",
    "Pi", "Gamma", "Lambda", "Phi", "Psi", "Theta",
    "infty", "sum", "prod", "int", "lim", "log", "ln", "sin", "cos", "tan",
    "cot", "sec", "csc", "arcsin", "arccos", "arctan",
    "le", "ge", "leq", "geq", "neq", "ne", "approx", "equiv", "propto",
    "in", "notin", "subset", "subseteq", "supset", "supseteq", "cap", "cup",
    "to", "rightarrow", "Rightarrow", "implies", "iff", "Leftrightarrow",
    "leftarrow", "Leftarrow", "rightleftharpoons",
    "cdot", "times", "div", "pm", "mp", "ast",
    "left", "right", "big", "Big", "bigg", "Bigg",
    "mathrm", "mathbf", "mathbb", "mathcal", "mathit", "mathsf", "text",
    "begin", "end",
    "vec", "hat", "bar", "tilde", "dot", "ddot", "overline", "underline",
    "binom", "tfrac", "dfrac",
    "circ", "degree", "prime",
    "therefore", "because",
}

CORRUPTION_TOKENS = {"eta", "rac", "ext", "ackslash", "alphaeta"}

# Regex patterns
_RE_COMMAND = re.compile(r"\\([a-zA-Z]+)")
_RE_SUPER = re.compile(r"[A-Za-z0-9}\)\]][\^][A-Za-z0-9{(\-]")
_RE_SUB = re.compile(r"[A-Za-z0-9}\)\]][_][A-Za-z0-9{(\-]")
_RE_ORPHAN_ETA = re.compile(r"(?<![\\A-Za-z])eta\b")
_RE_ORPHAN_RAC = re.compile(r"(?<![A-Za-z])rac\{")
_RE_ORPHAN_EXT = re.compile(r"(?<![\\A-Za-z])ext\{")
_RE_ALPHAETA = re.compile(r"alphaeta\b")
# Currency: $ followed by digits-with-optional-decimal/thousands, optionally followed by short prose
_RE_CURRENCY = re.compile(r"^\s*\d+(?:[,.]\d+)*\s*(?:[A-Za-z]{1,15}(?:\s+[A-Za-z]{1,15}){0,3})?\s*$")
_RE_PURE_ALPHA = re.compile(r"^[A-Za-z]{1,15}$")
_RE_HAS_DIGIT = re.compile(r"\d")
_RE_HAS_OPERATOR = re.compile(r"[+\-*/=<>^_]")
_RE_HAS_LATEX_LIKE = re.compile(r"\\[a-zA-Z]+|[\^_]\{")
_RE_FILL_BLANK = re.compile(r"_{3,}")
_RE_HTML = re.compile(r"<(table|tr|td|th|p|strong|br|thead|tbody|div|span)\b", re.I)

# Source-family priors (higher => more likely the field stores math without delimiters)
SOURCE_MATH_PRIOR = {
    "rubric_criterion": 0.85,
    "rubric_description": 0.45,
    "graded_step_working_line": 0.6,
    "graded_step_student_work": 0.5,
    "review_working_line": 0.55,
    "annotation_error_text": 0.55,
    "annotation_other": 0.4,
    "feedback": 0.25,
    "graded_step_desc": 0.3,
    "graded_step_explanation": 0.25,
    "ai_solution": 0.25,
    "ai_answer": 0.45,
    "expected_answer": 0.45,
    "student_answer": 0.15,
    "authored_question": 0.2,
    "question_short_prompt": 0.2,
}


@dataclass
class ClassificationResult:
    score: float           # [0,1] math-intent confidence
    is_math: bool          # convenience: score >= threshold
    signals: dict          # individual signal contributions, for telemetry
    corruption: bool       # one or more corruption tokens detected
    is_html: bool          # HTML detected — route to HTML path instead of math
    is_currency: bool      # currency-shaped content
    is_fill_blank: bool    # contains `_{3,}` runs


def family_of(field_path: Optional[str]) -> str:
    """Map a `field_path` to a source-family key. Mirrors _probe_fields.py."""
    if not field_path:
        return "unknown"
    s = field_path
    if ".ai_solution" in s: return "ai_solution"
    if ".ai_answer" in s:   return "ai_answer"
    if ".expected_answer" in s: return "expected_answer"
    if ".short_prompt" in s or "question_short_prompt" in s: return "question_short_prompt"
    if ".question_text" in s or ".options[" in s: return "authored_question"
    if "rubric_steps" in s and "criterion" in s: return "rubric_criterion"
    if "rubric_steps" in s and "description" in s: return "rubric_description"
    if "steps_breakdown" in s and "description" in s: return "graded_step_desc"
    if "steps_breakdown" in s and "student_work" in s: return "graded_step_student_work"
    if "steps_breakdown" in s and "working_lines" in s: return "graded_step_working_line"
    if "steps_breakdown" in s and "explanation" in s: return "graded_step_explanation"
    if "review_render.working_lines" in s: return "review_working_line"
    if "review_render.annotations" in s and "error_text" in s: return "annotation_error_text"
    if "review_render.annotations" in s: return "annotation_other"
    if "feedback" in s: return "feedback"
    if "student_answer" in s: return "student_answer"
    return "unknown"


def classify(content: str, *, source_family: str = "unknown", inside_math_delim: bool = False) -> ClassificationResult:
    """
    Score content for math intent.

    Args:
      content: the candidate math string (without delimiters)
      source_family: e.g. "rubric_criterion" — used as a prior
      inside_math_delim: True if `content` was already inside `$...$`; this
        raises confidence because the author signaled math intent.
    """
    signals: dict = {}

    # HTML short-circuit
    is_html = bool(_RE_HTML.search(content))
    if is_html:
        return ClassificationResult(
            score=0.0, is_math=False, signals={"html": True},
            corruption=False, is_html=True, is_currency=False, is_fill_blank=False
        )

    # Fill-in-the-blank short-circuit
    is_fill_blank = bool(_RE_FILL_BLANK.search(content))
    if is_fill_blank and not inside_math_delim:
        return ClassificationResult(
            score=0.0, is_math=False, signals={"fill_blank": True},
            corruption=False, is_html=False, is_currency=False, is_fill_blank=True
        )

    # Corruption detection
    corruption_hits = []
    if _RE_ORPHAN_ETA.search(content):    corruption_hits.append("eta")
    if _RE_ORPHAN_RAC.search(content):    corruption_hits.append("rac")
    if _RE_ORPHAN_EXT.search(content):    corruption_hits.append("ext")
    if _RE_ALPHAETA.search(content):      corruption_hits.append("alphaeta")
    corruption = bool(corruption_hits)
    if corruption:
        signals["corruption"] = corruption_hits

    # Currency detection (only when not already inside a math delimiter)
    is_currency = bool(_RE_CURRENCY.match(content)) and not inside_math_delim
    if is_currency:
        signals["currency"] = True
        return ClassificationResult(
            score=0.05, is_math=False, signals=signals,
            corruption=corruption, is_html=False, is_currency=True, is_fill_blank=False
        )

    # Recognized commands
    cmds = [m.group(1) for m in _RE_COMMAND.finditer(content)]
    known_cmds = [c for c in cmds if c in MATH_COMMANDS]
    if known_cmds:
        signals["known_commands"] = len(known_cmds)
    if cmds:
        signals["total_commands"] = len(cmds)

    # Sub/super adjacency
    n_super = len(_RE_SUPER.findall(content))
    n_sub = len(_RE_SUB.findall(content))
    if n_super: signals["super"] = n_super
    if n_sub: signals["sub"] = n_sub

    # Math operator density
    n_op = len(_RE_HAS_OPERATOR.findall(content))
    n_digit = len(_RE_HAS_DIGIT.findall(content))
    if n_op: signals["operators"] = n_op
    if n_digit: signals["digits"] = n_digit

    # Pure alphabetic short token — likely a variable name; only math if inside delim
    pure_alpha = bool(_RE_PURE_ALPHA.match(content.strip()))
    if pure_alpha: signals["pure_alpha_token"] = True

    # Score assembly
    score = 0.0
    if inside_math_delim:
        score += 0.6  # author opted in
    score += SOURCE_MATH_PRIOR.get(source_family, 0.3) * 0.15
    score += min(0.35, 0.12 * len(known_cmds))
    score += min(0.15, 0.05 * (n_super + n_sub))
    if n_op >= 2 and n_digit >= 1:
        score += 0.1
    if corruption:
        # Corruption means a backslash was lost: the underlying intent IS math,
        # we just can't render it safely without repair. Slight boost so the
        # repair pipeline runs, but don't push past threshold on its own.
        score += 0.15
    if pure_alpha and not inside_math_delim:
        score -= 0.4

    score = max(0.0, min(1.0, score))
    is_math = score >= 0.55

    return ClassificationResult(
        score=score, is_math=is_math, signals=signals,
        corruption=corruption, is_html=False, is_currency=False, is_fill_blank=False,
    )
