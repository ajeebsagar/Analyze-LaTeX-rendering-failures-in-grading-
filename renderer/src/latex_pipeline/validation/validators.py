"""Validation: each rule is one IValidator (SRP). CompositeValidator chains
them (Composite Pattern + OCP — add a rule by injecting a new IValidator)."""
from __future__ import annotations

import re
from typing import List

from ..core import IValidator, ValidationResult


_RE_COMMAND = re.compile(r"\\([a-zA-Z]+)")
_RE_SUB_RUN = re.compile(r"_{3,}")


class NonEmptyValidator(IValidator):
    @property
    def name(self): return "non_empty"
    def validate(self, content):
        if not content or not content.strip():
            return ValidationResult(False, ["empty_math_segment"])
        return ValidationResult(True, [])


class MaxLengthValidator(IValidator):
    def __init__(self, max_length: int = 8000):
        self._max = max_length
    @property
    def name(self): return "max_length"
    def validate(self, content):
        if len(content) > self._max:
            return ValidationResult(False, ["exceeds_max_length"])
        return ValidationResult(True, [])


class BraceBalanceValidator(IValidator):
    def __init__(self, max_depth: int = 32):
        self._max_depth = max_depth
    @property
    def name(self): return "brace_balance"
    def validate(self, content):
        depth = 0
        max_depth = 0
        i = 0
        n = len(content)
        reasons: List[str] = []
        while i < n:
            c = content[i]
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "{":
                depth += 1
                if depth > max_depth: max_depth = depth
            elif c == "}":
                depth -= 1
                if depth < 0:
                    reasons.append("unbalanced_close_brace")
                    break
            i += 1
        if depth != 0 and "unbalanced_close_brace" not in reasons:
            reasons.append("unbalanced_brace_count")
        if max_depth > self._max_depth:
            reasons.append("brace_depth_exceeded")
        return ValidationResult(not reasons, reasons)


class SubscriptRunValidator(IValidator):
    """Reject `___` style fill-in-the-blank — KaTeX builds a nested subscript chain."""
    @property
    def name(self): return "subscript_run"
    def validate(self, content):
        if _RE_SUB_RUN.search(content):
            return ValidationResult(False, ["subscript_run_too_long"])
        return ValidationResult(True, [])


class ForbiddenCommandValidator(IValidator):
    DEFAULT_FORBIDDEN = frozenset({
        "input", "include", "write", "openout", "closeout", "immediate",
        "csname", "endcsname", "loop", "repeat", "newif",
        "href", "url", "includegraphics",
    })

    def __init__(self, forbidden: set[str] | frozenset[str] | None = None):
        self._forbidden = frozenset(forbidden) if forbidden else self.DEFAULT_FORBIDDEN

    @property
    def name(self): return "forbidden_command"
    def validate(self, content):
        for m in _RE_COMMAND.finditer(content):
            if m.group(1) in self._forbidden:
                return ValidationResult(False, [f"forbidden_command:{m.group(1)}"])
        return ValidationResult(True, [])


class CompositeValidator(IValidator):
    """Runs a list of validators and accumulates reasons (Composite pattern)."""
    def __init__(self, validators: List[IValidator]):
        self._validators = list(validators)

    @property
    def name(self): return "composite"
    def validate(self, content):
        reasons: List[str] = []
        for v in self._validators:
            r = v.validate(content)
            if not r.ok:
                reasons.extend(r.reasons)
        return ValidationResult(not reasons, reasons)


def default_validators() -> CompositeValidator:
    return CompositeValidator([
        NonEmptyValidator(),
        MaxLengthValidator(),
        BraceBalanceValidator(),
        SubscriptRunValidator(),
        ForbiddenCommandValidator(),
    ])
