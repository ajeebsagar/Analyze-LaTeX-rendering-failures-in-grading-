"""latex_pipeline — SOLID-structured self-healing LaTeX rendering pipeline.

Public API:
  - build_default_pipeline()   factory for the default Pipeline
  - PipelineBuilder            fluent DI builder for custom pipelines
  - heal(text, family)         one-liner that returns healed text
"""
from .pipeline import Pipeline, PipelineBuilder, build_default_pipeline
from .core import PipelineResult, RenderOutcome, SegmentKind
from .buckets import BUCKET_DESCRIPTIONS
from .diagnostics import ErrorAnalyzer, ErrorReport, ErrorIssue

_default_pipeline: Pipeline | None = None


def _get_default():
    global _default_pipeline
    if _default_pipeline is None:
        _default_pipeline = build_default_pipeline()
    return _default_pipeline


def heal(text: str, *, source_family: str = "rubric_criterion",
         field_path: str | None = None) -> PipelineResult:
    """Auto-heal a LaTeX string. Returns the full PipelineResult.

    Convenience entry point — wires the default pipeline lazily.
    """
    pipeline = _get_default()
    return pipeline.run(text, source_family=source_family, field_path=field_path)


__all__ = [
    "Pipeline", "PipelineBuilder", "build_default_pipeline",
    "PipelineResult", "RenderOutcome", "SegmentKind",
    "BUCKET_DESCRIPTIONS", "heal",
    "ErrorAnalyzer", "ErrorReport", "ErrorIssue",
]
