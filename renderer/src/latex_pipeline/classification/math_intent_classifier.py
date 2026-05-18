"""Composes ISignalDetector implementations into a ClassificationResult.

SRP: the classifier does NOT know how to detect individual signals; it only
combines them into a score. Adding a new signal type means injecting a new
ISignalDetector (OCP).
"""
from __future__ import annotations

from typing import List

from ..core import ClassificationResult, IFamilyResolver, IMathIntentClassifier, ISignalDetector


class MathIntentClassifier(IMathIntentClassifier):
    """Default classifier. Depends only on the ISignalDetector + IFamilyResolver
    abstractions (DIP)."""

    def __init__(self,
                 detectors: List[ISignalDetector],
                 family_resolver: IFamilyResolver,
                 *,
                 math_threshold: float = 0.55,
                 family_weight: float = 0.15,
                 inside_delim_boost: float = 0.6):
        self._detectors = list(detectors)
        self._family_resolver = family_resolver
        self._math_threshold = math_threshold
        self._family_weight = family_weight
        self._inside_delim_boost = inside_delim_boost

    def classify(self, content, *, source_family="unknown", inside_math_delim=False):
        signals: dict = {}
        flags = {"is_html": False, "is_currency": False, "is_fill_blank": False, "has_corruption": False}
        score = 0.0

        if inside_math_delim:
            score += self._inside_delim_boost

        # Family prior contribution
        prior = self._family_resolver.prior_for(source_family)
        score += prior * self._family_weight

        # Run all detectors
        for det in self._detectors:
            try:
                out = det.detect(content, inside_math_delim=inside_math_delim)
            except Exception:
                continue  # detector exceptions never break classification
            if not out:
                continue
            if "score" in out:
                score += out["score"]
            if "signals" in out:
                signals.update(out["signals"])
            if "flags" in out:
                for k, v in out["flags"].items():
                    if v:
                        flags[k] = True

        # Short-circuit on HTML / fill-blank / currency (always non-math)
        if flags["is_html"]:
            return ClassificationResult(score=0.0, signals=signals, is_math=False,
                                        is_html=True, has_corruption=flags["has_corruption"])
        if flags["is_fill_blank"]:
            return ClassificationResult(score=0.0, signals=signals, is_math=False,
                                        is_fill_blank=True, has_corruption=flags["has_corruption"])
        if flags["is_currency"]:
            return ClassificationResult(score=max(0.0, score), signals=signals, is_math=False,
                                        is_currency=True, has_corruption=flags["has_corruption"])

        score = max(0.0, min(1.0, score))
        return ClassificationResult(
            score=score,
            signals=signals,
            is_math=score >= self._math_threshold,
            is_html=False,
            is_currency=False,
            is_fill_blank=False,
            has_corruption=flags["has_corruption"],
        )

    @property
    def math_threshold(self) -> float:
        return self._math_threshold
