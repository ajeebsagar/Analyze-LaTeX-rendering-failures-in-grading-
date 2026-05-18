"""Maps DB field_paths to source-family identifiers and math priors.

SRP: ONLY knows about field-path -> family mapping. Extending with a new
family means adding a row, not modifying logic (OCP via data table).
"""
from __future__ import annotations

from typing import Optional

from ..core import IFamilyResolver


_FAMILY_RULES = (
    # (substring, family_name)
    (".ai_solution", "ai_solution"),
    (".ai_answer", "ai_answer"),
    (".expected_answer", "expected_answer"),
    (".short_prompt", "question_short_prompt"),
    ("question_short_prompt", "question_short_prompt"),
    (".question_text", "authored_question"),
    (".options[", "authored_question"),
)

_COMPLEX_RULES = (
    # (matcher_function, family_name)
    (lambda s: "rubric_steps" in s and "criterion" in s, "rubric_criterion"),
    (lambda s: "rubric_steps" in s and "description" in s, "rubric_description"),
    (lambda s: "steps_breakdown" in s and "description" in s, "graded_step_desc"),
    (lambda s: "steps_breakdown" in s and "student_work" in s, "graded_step_student_work"),
    (lambda s: "steps_breakdown" in s and "working_lines" in s, "graded_step_working_line"),
    (lambda s: "steps_breakdown" in s and "explanation" in s, "graded_step_explanation"),
    (lambda s: "review_render.working_lines" in s, "review_working_line"),
    (lambda s: "review_render.annotations" in s and "error_text" in s, "annotation_error_text"),
    (lambda s: "review_render.annotations" in s, "annotation_other"),
    (lambda s: "feedback" in s, "feedback"),
    (lambda s: "student_answer" in s, "student_answer"),
)

# Source-family priors: how likely a field stores math without delimiters.
DEFAULT_PRIORS = {
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
    "unknown": 0.3,
}


class DefaultFamilyResolver(IFamilyResolver):
    """Default implementation. Easily replaced with a config-driven version."""

    def __init__(self, priors: dict[str, float] | None = None):
        self._priors = dict(DEFAULT_PRIORS)
        if priors:
            self._priors.update(priors)

    def family_of(self, field_path: Optional[str]) -> str:
        if not field_path:
            return "unknown"
        # Complex rules first (more specific)
        for matcher, fam in _COMPLEX_RULES:
            if matcher(field_path):
                return fam
        # Simple substring rules
        for needle, fam in _FAMILY_RULES:
            if needle in field_path:
                return fam
        return "unknown"

    def prior_for(self, family: str) -> float:
        return self._priors.get(family, self._priors["unknown"])
