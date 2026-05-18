"""Pipeline-internal exceptions. Pipeline callers should never see these
escape — they are caught and converted to a fallback span. Their presence
in logs is always a bug.
"""


class LatexPipelineError(Exception):
    """Base class for any error originating inside the pipeline."""


class InvalidSegmentError(LatexPipelineError):
    """A segment object has inconsistent fields (start>end, kind unknown, ...)."""
