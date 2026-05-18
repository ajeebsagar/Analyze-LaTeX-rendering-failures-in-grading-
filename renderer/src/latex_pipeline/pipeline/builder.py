"""PipelineBuilder — fluent DI builder.

This is the ONLY place that knows about concrete implementations. To swap a
component (Liskov Substitution), call the corresponding `with_*` method
before `.build()`. The default constructor wires the production stack.
"""
from __future__ import annotations

from typing import List, Optional

from ..buckets import BucketLabeler
from ..classification import DefaultFamilyResolver, MathIntentClassifier, default_signal_detectors
from ..core import (
    IBucketLabeler, IFallbackRenderer, IFamilyResolver, IMathIntentClassifier,
    IRepairer, ISegmenter, ISignalDetector, IValidator,
)
from ..fallback import HtmlFallbackRenderer
from ..repair import (
    default_tier1_global, default_tier1_math, default_tier1_prose,
    default_tier2_global, default_tier2_math,
)
from ..segmentation import StateMachineSegmenter
from ..validation import default_validators
from .pipeline import Pipeline


class PipelineBuilder:
    """Fluent builder. Each `with_*` returns `self` for chaining."""

    def __init__(self):
        self._segmenter: Optional[ISegmenter] = None
        self._family_resolver: Optional[IFamilyResolver] = None
        self._classifier: Optional[IMathIntentClassifier] = None
        self._signal_detectors: Optional[List[ISignalDetector]] = None
        self._validator: Optional[IValidator] = None
        self._fallback: Optional[IFallbackRenderer] = None
        self._bucket_labeler: Optional[IBucketLabeler] = None
        self._tier1_global: Optional[List[IRepairer]] = None
        self._tier1_math: Optional[List[IRepairer]] = None
        self._tier1_prose: Optional[List[IRepairer]] = None
        self._tier2_global: Optional[List[IRepairer]] = None
        self._tier2_math: Optional[List[IRepairer]] = None
        self._repair_threshold: float = 0.7

    # ---- Component overrides (LSP / DIP) ----
    def with_segmenter(self, s: ISegmenter):
        self._segmenter = s; return self
    def with_family_resolver(self, f: IFamilyResolver):
        self._family_resolver = f; return self
    def with_classifier(self, c: IMathIntentClassifier):
        self._classifier = c; return self
    def with_signal_detectors(self, ds: List[ISignalDetector]):
        self._signal_detectors = list(ds); return self
    def add_signal_detector(self, d: ISignalDetector):
        if self._signal_detectors is None:
            self._signal_detectors = default_signal_detectors()
        self._signal_detectors.append(d); return self
    def with_validator(self, v: IValidator):
        self._validator = v; return self
    def with_fallback(self, f: IFallbackRenderer):
        self._fallback = f; return self
    def with_bucket_labeler(self, b: IBucketLabeler):
        self._bucket_labeler = b; return self
    def with_tier1_global(self, rs: List[IRepairer]):
        self._tier1_global = list(rs); return self
    def with_tier1_math(self, rs: List[IRepairer]):
        self._tier1_math = list(rs); return self
    def with_tier1_prose(self, rs: List[IRepairer]):
        self._tier1_prose = list(rs); return self
    def with_tier2_global(self, rs: List[IRepairer]):
        self._tier2_global = list(rs); return self
    def with_tier2_math(self, rs: List[IRepairer]):
        self._tier2_math = list(rs); return self
    def add_tier2_math_repairer(self, r: IRepairer):
        if self._tier2_math is None:
            self._tier2_math = default_tier2_math()
        self._tier2_math.append(r); return self
    def with_repair_threshold(self, t: float):
        self._repair_threshold = t; return self

    # ---- Build ----
    def build(self) -> Pipeline:
        segmenter = self._segmenter or StateMachineSegmenter()
        family_resolver = self._family_resolver or DefaultFamilyResolver()
        signal_detectors = self._signal_detectors or default_signal_detectors()
        classifier = self._classifier or MathIntentClassifier(signal_detectors, family_resolver)
        validator = self._validator or default_validators()
        fallback = self._fallback or HtmlFallbackRenderer()
        bucket_labeler = self._bucket_labeler or BucketLabeler()
        t1g = self._tier1_global if self._tier1_global is not None else default_tier1_global()
        t1m = self._tier1_math if self._tier1_math is not None else default_tier1_math()
        t1p = self._tier1_prose if self._tier1_prose is not None else default_tier1_prose()
        t2g = self._tier2_global if self._tier2_global is not None else default_tier2_global()
        t2m = self._tier2_math if self._tier2_math is not None else default_tier2_math()
        return Pipeline(
            segmenter=segmenter,
            classifier=classifier,
            family_resolver=family_resolver,
            validator=validator,
            fallback_renderer=fallback,
            bucket_labeler=bucket_labeler,
            tier1_global=t1g, tier1_math=t1m, tier1_prose=t1p,
            tier2_global=t2g, tier2_math=t2m,
            repair_confidence_threshold=self._repair_threshold,
        )


def build_default_pipeline() -> Pipeline:
    """One-liner: get the production-default pipeline."""
    return PipelineBuilder().build()
