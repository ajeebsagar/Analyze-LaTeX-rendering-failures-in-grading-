"""Core layer: abstract interfaces, value objects, exceptions.

Higher layers depend ONLY on this module (Dependency Inversion Principle).
Implementations live in sibling modules.
"""
from .interfaces import (
    ISegmenter, ISignalDetector, IMathIntentClassifier, IRepairer,
    IValidator, IBucketLabeler, IFallbackRenderer, IFamilyResolver,
)
from .models import (
    Segment, SegmentKind, SegmentResult, RenderOutcome,
    ClassificationResult, ValidationResult, RepairOutcome,
    PipelineResult,
)
from .exceptions import LatexPipelineError, InvalidSegmentError

__all__ = [
    # interfaces
    "ISegmenter", "ISignalDetector", "IMathIntentClassifier", "IRepairer",
    "IValidator", "IBucketLabeler", "IFallbackRenderer", "IFamilyResolver",
    # models
    "Segment", "SegmentKind", "SegmentResult", "RenderOutcome",
    "ClassificationResult", "ValidationResult", "RepairOutcome",
    "PipelineResult",
    # exceptions
    "LatexPipelineError", "InvalidSegmentError",
]
