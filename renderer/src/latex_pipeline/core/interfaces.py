"""Abstract interfaces.

Every concrete implementation in higher layers satisfies one of these
Protocols. The Pipeline orchestrator depends only on these abstractions
(Dependency Inversion Principle), so any component can be swapped without
modifying the orchestrator (Open/Closed Principle).
"""
from __future__ import annotations

from typing import List, Protocol, runtime_checkable

from .models import (
    ClassificationResult, PipelineResult, RepairOutcome, Segment, SegmentResult,
    ValidationResult,
)


@runtime_checkable
class ISegmenter(Protocol):
    """Splits a raw string into Segment objects. Stateless."""
    def segment(self, text: str) -> List[Segment]: ...


@runtime_checkable
class IFamilyResolver(Protocol):
    """Maps a field_path to a source-family identifier + math prior."""
    def family_of(self, field_path: str | None) -> str: ...
    def prior_for(self, family: str) -> float: ...


@runtime_checkable
class ISignalDetector(Protocol):
    """One detector contributes signals + score deltas to the classifier.

    Implementations are composed (Open/Closed): adding a new signal type
    means adding a new detector, never editing existing ones.
    """
    @property
    def name(self) -> str: ...
    def detect(self, content: str, *, inside_math_delim: bool) -> dict:
        """Return a dict with optional keys: 'score', 'signals', 'flags'.
        - score: float added to base classifier score
        - signals: dict merged into ClassificationResult.signals
        - flags: dict with optional 'is_html', 'is_currency', 'is_fill_blank',
                 'has_corruption' overrides.
        """
        ...


@runtime_checkable
class IMathIntentClassifier(Protocol):
    """Produces a ClassificationResult from content + source-family prior."""
    def classify(self, content: str, *, source_family: str,
                 inside_math_delim: bool = False) -> ClassificationResult: ...


@runtime_checkable
class IRepairer(Protocol):
    """One repair operation. Applied to either a math segment or a prose
    segment depending on `scope`. Must be idempotent.
    """
    @property
    def name(self) -> str: ...
    @property
    def scope(self) -> str:
        """One of: 'global', 'math', 'prose'."""
        ...
    def repair(self, text: str, *, classification: ClassificationResult | None = None,
               family_prior: float = 0.0) -> RepairOutcome: ...


@runtime_checkable
class IValidator(Protocol):
    """One validation rule. Composable with CompositeValidator."""
    @property
    def name(self) -> str: ...
    def validate(self, content: str) -> ValidationResult: ...


@runtime_checkable
class IBucketLabeler(Protocol):
    """Maps a final PipelineResult + original input to one or more bucket labels."""
    def label(self, original_text: str, result: PipelineResult) -> List[str]: ...


@runtime_checkable
class IFallbackRenderer(Protocol):
    """Emits a safe HTML representation for content the pipeline could not render."""
    def render(self, content: str, *, reason: str) -> str: ...
