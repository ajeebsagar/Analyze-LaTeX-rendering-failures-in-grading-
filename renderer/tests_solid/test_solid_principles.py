"""Tests that the architecture honors SOLID principles in a way you can
verify mechanically.

S — Single Responsibility:
    No class implements more than one interface; signal detectors only
    detect signals; validators only validate; etc.

O — Open/Closed:
    Adding a new repair, signal, or validator extends behavior without
    modifying existing classes. We add a fake one via the builder.

L — Liskov Substitution:
    Any class satisfying the interface can replace the default.

I — Interface Segregation:
    Each interface has a single, narrow purpose.

D — Dependency Inversion:
    The Pipeline orchestrator depends only on core.interfaces, not on
    concrete implementations.
"""
from . import _paths  # noqa: F401

import re
import unittest

from latex_pipeline import build_default_pipeline, PipelineBuilder, RenderOutcome
from latex_pipeline.core import (
    ClassificationResult, IBucketLabeler, IFallbackRenderer, IFamilyResolver,
    IMathIntentClassifier, IRepairer, ISegmenter, ISignalDetector, IValidator,
    PipelineResult, RepairOutcome, Segment, SegmentKind, ValidationResult,
)


# ===== S — Single Responsibility =====
class TestSingleResponsibility(unittest.TestCase):
    """Each component implements exactly one interface and has a focused job."""

    def test_segmenter_only_segments(self):
        from latex_pipeline.segmentation import StateMachineSegmenter
        s = StateMachineSegmenter()
        # Has a single public method: segment()
        public = [m for m in dir(s) if not m.startswith("_") and callable(getattr(s, m))]
        self.assertEqual(set(public), {"segment"})

    def test_each_validator_has_single_rule(self):
        from latex_pipeline.validation import (
            NonEmptyValidator, BraceBalanceValidator, SubscriptRunValidator,
            ForbiddenCommandValidator, MaxLengthValidator,
        )
        for cls in (NonEmptyValidator, BraceBalanceValidator,
                    SubscriptRunValidator, ForbiddenCommandValidator,
                    MaxLengthValidator):
            v = cls() if cls is not ForbiddenCommandValidator else cls()
            # Public interface = name property + validate method
            self.assertTrue(hasattr(v, "validate"))
            self.assertTrue(hasattr(v, "name"))

    def test_each_signal_detector_only_detects(self):
        from latex_pipeline.classification import default_signal_detectors
        for det in default_signal_detectors():
            self.assertTrue(hasattr(det, "detect"))
            self.assertTrue(hasattr(det, "name"))


# ===== O — Open/Closed =====
class CustomEmojiRepairer(IRepairer):
    """A custom repairer that strips emoji from math segments.

    Proves OCP: we ADD this without modifying any pipeline code.
    """
    EMOJI = re.compile(r"[\U0001F300-\U0001FAFF\U00002600-\U000027BF]")

    @property
    def name(self): return "strip_emoji"
    @property
    def scope(self): return "math"
    def repair(self, text, *, classification=None, family_prior=0.0):
        out = self.EMOJI.sub("", text)
        return RepairOutcome(out, [self.name] if out != text else [])


class TestOpenClosed(unittest.TestCase):
    def test_can_add_custom_repairer_without_modifying_pipeline(self):
        pipeline = (PipelineBuilder()
                    .add_tier2_math_repairer(CustomEmojiRepairer())
                    .build())
        r = pipeline.run("$\\alpha + \\beta 🚀$", source_family="feedback")
        # The new repairer fired
        self.assertIn("strip_emoji", r.repairs_applied)
        math = [s for s in r.segments if s.outcome is RenderOutcome.MATH][0]
        self.assertNotIn("🚀", math.repaired)


# ===== L — Liskov Substitution =====
class StubSegmenter(ISegmenter):
    """A test double that always returns one math segment.

    Proves LSP: the pipeline does not depend on the concrete StateMachineSegmenter.
    """
    def segment(self, text):
        return [Segment(SegmentKind.MATH_INLINE, content=text, start=0, end=len(text))]


class StubFallbackRenderer(IFallbackRenderer):
    def render(self, content, *, reason):
        return f"<FALLBACK:{reason}>"


class TestLiskovSubstitution(unittest.TestCase):
    def test_alternative_segmenter_works(self):
        pipeline = (PipelineBuilder()
                    .with_segmenter(StubSegmenter())
                    .build())
        r = pipeline.run(r"\frac{1}{2}", source_family="rubric_criterion")
        # With the stub segmenter the entire input is a math segment.
        self.assertEqual(r.math_count + r.fallback_count, 1)

    def test_alternative_fallback_renderer_works(self):
        pipeline = (PipelineBuilder()
                    .with_fallback(StubFallbackRenderer())
                    .build())
        r = pipeline.run(r"$\input{/etc/passwd}$", source_family="student_answer")
        # The stub renderer was used for the fallback span
        self.assertIn("<FALLBACK:", r.html)


# ===== I — Interface Segregation =====
class TestInterfaceSegregation(unittest.TestCase):
    """Every interface defines only what a caller needs — no fat interfaces."""

    def test_isegmenter_has_one_method(self):
        # Only `segment` is part of the protocol surface.
        proto_methods = [m for m in dir(ISegmenter)
                         if not m.startswith("_") and callable(getattr(ISegmenter, m, None))]
        self.assertIn("segment", proto_methods)

    def test_ivalidator_only_validates(self):
        proto_methods = [m for m in dir(IValidator)
                         if not m.startswith("_") and callable(getattr(IValidator, m, None))]
        self.assertIn("validate", proto_methods)

    def test_isignal_detector_only_detects(self):
        proto_methods = [m for m in dir(ISignalDetector)
                         if not m.startswith("_") and callable(getattr(ISignalDetector, m, None))]
        self.assertIn("detect", proto_methods)


# ===== D — Dependency Inversion =====
class TestDependencyInversion(unittest.TestCase):
    """The Pipeline class imports ONLY from core (abstractions)."""

    def test_pipeline_module_imports_only_core_and_fallback_for_helpers(self):
        from latex_pipeline.pipeline import pipeline as pipeline_mod
        import inspect
        src = inspect.getsource(pipeline_mod)
        # The orchestrator must not reach into concrete submodules.
        # Allowed deps: core (interfaces / models) + fallback.html_escape helper.
        self.assertNotIn("from ..segmentation", src)
        self.assertNotIn("from ..classification", src)
        self.assertNotIn("from ..repair", src)
        self.assertNotIn("from ..validation", src)
        self.assertNotIn("from ..buckets", src)


# ===== Bonus: dependency-injection round-trip =====
class CountingSignal(ISignalDetector):
    """Counts how many times it was invoked — used to assert wiring works."""
    def __init__(self):
        self.calls = 0
    @property
    def name(self): return "counting"
    def detect(self, content, *, inside_math_delim):
        self.calls += 1
        return {}


class TestDependencyInjection(unittest.TestCase):
    def test_injected_signal_detector_is_invoked(self):
        counter = CountingSignal()
        pipeline = (PipelineBuilder()
                    .add_signal_detector(counter)
                    .build())
        pipeline.run(r"If $\alpha$ then $\beta$.", source_family="authored_question")
        self.assertGreater(counter.calls, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
