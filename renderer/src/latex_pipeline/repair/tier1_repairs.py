"""Tier 1 repairs: deterministic, unconditional, always idempotent."""
from __future__ import annotations

import re
import unicodedata
from typing import List

from ..core import IRepairer, RepairOutcome


_COMBINING_RE = re.compile(r"[̀-ͯ]")
_LITERAL_NEWLINE = re.compile(r"\\n(?=[A-Z]|\s|$)")
_LITERAL_TAB = re.compile(r"\\t(?=\s|$)")
_LITERAL_CR = re.compile(r"\\r(?=\s|$)")


class NfcNormalizer(IRepairer):
    """Unicode NFC normalize. Global scope."""
    @property
    def name(self): return "nfc_normalize"
    @property
    def scope(self): return "global"
    def repair(self, text, *, classification=None, family_prior=0.0):
        out = unicodedata.normalize("NFC", text)
        return RepairOutcome(out, [self.name] if out != text else [])


class DiacriticStripper(IRepairer):
    """Strip combining diacritics (U+0300..U+036F). Math-segment scope."""
    @property
    def name(self): return "strip_combining_diacritics"
    @property
    def scope(self): return "math"
    def repair(self, text, *, classification=None, family_prior=0.0):
        out = _COMBINING_RE.sub("", text)
        return RepairOutcome(out, [self.name] if out != text else [])


class LiteralEscapeRepairer(IRepairer):
    """Convert literal \\n, \\t, \\r escapes back to real whitespace.
    Prose-segment scope only — math segments must keep their backslash-escaped
    commands intact."""
    @property
    def name(self): return "literal_escape_to_whitespace"
    @property
    def scope(self): return "prose"
    def repair(self, text, *, classification=None, family_prior=0.0):
        out = _LITERAL_NEWLINE.sub("\n", text)
        out = _LITERAL_TAB.sub("\t", out)
        out = _LITERAL_CR.sub("\r", out)
        return RepairOutcome(out, [self.name] if out != text else [])


def default_tier1_global() -> List[IRepairer]:
    return [NfcNormalizer()]


def default_tier1_math() -> List[IRepairer]:
    return [DiacriticStripper()]


def default_tier1_prose() -> List[IRepairer]:
    return [LiteralEscapeRepairer()]
