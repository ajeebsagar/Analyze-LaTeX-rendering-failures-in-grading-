"""Value objects shared across layers. Pure data, no behavior."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class SegmentKind(str, Enum):
    TEXT = "text"
    MATH_INLINE = "math_inline"
    MATH_DISPLAY = "math_display"
    MATH_PAREN = "math_paren"
    MATH_BRACKET = "math_bracket"
    HTML = "html"

    @property
    def is_math(self) -> bool:
        return self in (
            SegmentKind.MATH_INLINE, SegmentKind.MATH_DISPLAY,
            SegmentKind.MATH_PAREN, SegmentKind.MATH_BRACKET,
        )

    @property
    def is_display(self) -> bool:
        return self in (SegmentKind.MATH_DISPLAY, SegmentKind.MATH_BRACKET)


class RenderOutcome(str, Enum):
    MATH = "math"        # rendered as KaTeX math
    TEXT = "text"        # rendered as escaped prose
    FALLBACK = "fallback"  # validation rejected; rendered as labeled span
    HTML = "html"        # routed to HTML render path


@dataclass(frozen=True)
class Segment:
    """A raw segment produced by the segmentation stage."""
    kind: SegmentKind
    content: str  # raw inside-delimiter content for math; raw chars for text/html
    start: int
    end: int


@dataclass(frozen=True)
class ClassificationResult:
    """Output of the math-intent classifier."""
    score: float                       # [0, 1]
    signals: Dict[str, Any] = field(default_factory=dict)
    is_math: bool = False
    is_html: bool = False
    is_currency: bool = False
    is_fill_blank: bool = False
    has_corruption: bool = False


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    reasons: List[str] = field(default_factory=list)


@dataclass
class RepairOutcome:
    """Mutable so a pipeline stage can accumulate multiple repair names."""
    text: str
    applied: List[str] = field(default_factory=list)


@dataclass
class SegmentResult:
    """Final per-segment state. Constructed by the pipeline stages."""
    kind: SegmentKind
    original: str
    repaired: str
    classification: ClassificationResult
    repairs: List[str] = field(default_factory=list)
    validation: ValidationResult = field(default_factory=lambda: ValidationResult(True, []))
    outcome: RenderOutcome = RenderOutcome.TEXT
    prepared: str = ""
    html: str = ""


@dataclass
class PipelineResult:
    """Final output. The HTML and prepared text are stable, KaTeX-ready."""
    prepared_text: str
    html: str
    segments: List[SegmentResult] = field(default_factory=list)
    repairs_applied: List[str] = field(default_factory=list)
    failure_reasons: List[str] = field(default_factory=list)
    buckets: List[str] = field(default_factory=list)

    @property
    def fallback_count(self) -> int:
        return sum(1 for s in self.segments if s.outcome is RenderOutcome.FALLBACK)

    @property
    def math_count(self) -> int:
        return sum(1 for s in self.segments if s.outcome is RenderOutcome.MATH)
