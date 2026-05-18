"""Pipeline orchestrator.

DIP: depends on the abstractions in core.interfaces. The builder injects
concrete implementations. The orchestrator does not import any concrete
class directly.
"""
from __future__ import annotations

import re
from typing import List, Optional

from ..core import (
    ClassificationResult, IBucketLabeler, IFallbackRenderer, IFamilyResolver,
    IMathIntentClassifier, IRepairer, ISegmenter, IValidator,
    PipelineResult, RenderOutcome, Segment, SegmentKind, SegmentResult,
    ValidationResult,
)
from ..fallback import html_escape


_RE_HTML = re.compile(r"<(table|tr|td|th|p|strong|br|thead|tbody|div|span)\b", re.I)
# Whitelisted tags that we pass through verbatim in HTML-aware mode.
_ALLOWED_HTML_TAGS = frozenset({
    "table","thead","tbody","tfoot","tr","td","th","colgroup","col","caption",
    "p","br","strong","em","b","i","u","s",
    "ul","ol","li","dl","dt","dd",
    "h1","h2","h3","h4","h5","h6",
    "div","span","sub","sup",
    "code","pre",
    "hr",
})
# Tokenize HTML tags vs prose. Captures every <...> block as a tag token.
_RE_HTML_TAG = re.compile(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>")


class Pipeline:
    """End-to-end orchestrator: detect -> classify -> repair -> validate -> emit."""

    def __init__(self,
                 *,
                 segmenter: ISegmenter,
                 classifier: IMathIntentClassifier,
                 family_resolver: IFamilyResolver,
                 validator: IValidator,
                 fallback_renderer: IFallbackRenderer,
                 bucket_labeler: IBucketLabeler,
                 tier1_global: List[IRepairer],
                 tier1_math: List[IRepairer],
                 tier1_prose: List[IRepairer],
                 tier2_global: List[IRepairer],
                 tier2_math: List[IRepairer],
                 repair_confidence_threshold: float = 0.7):
        self._segmenter = segmenter
        self._classifier = classifier
        self._family_resolver = family_resolver
        self._validator = validator
        self._fallback = fallback_renderer
        self._bucket_labeler = bucket_labeler
        self._tier1_global = list(tier1_global)
        self._tier1_math = list(tier1_math)
        self._tier1_prose = list(tier1_prose)
        self._tier2_global = list(tier2_global)
        self._tier2_math = list(tier2_math)
        self._repair_threshold = repair_confidence_threshold

    # ------------------------------------------------------------------
    # Public API

    def run(self, text: Optional[str], *,
            field_path: Optional[str] = None,
            source_family: Optional[str] = None) -> PipelineResult:
        if text is None:
            text = ""

        family = source_family or self._family_resolver.family_of(field_path)
        family_prior = self._family_resolver.prior_for(family)

        # Stage 0: HTML-aware processing.
        # If the input contains whitelisted HTML tags, we split it into
        # (html-tag, non-tag-prose) chunks. Tags pass through verbatim;
        # prose runs through the full math pipeline. This means a row like
        #   "Find the mean: <table>...</table> when $x > 0$"
        # produces a sequence: text→html→text→math, NOT a single fallback.
        if _RE_HTML.search(text):
            return self._run_html_aware(text, family=family, family_prior=family_prior)

        # Stage 1: Tier 1 global transforms
        repairs_applied: List[str] = []
        for r in self._tier1_global:
            outcome = r.repair(text, family_prior=family_prior)
            text = outcome.text
            repairs_applied.extend(outcome.applied)

        # Stage 2: Tier 2 global (e.g. math-only wrapping)
        for r in self._tier2_global:
            outcome = r.repair(text, family_prior=family_prior)
            text = outcome.text
            repairs_applied.extend(outcome.applied)

        # Stage 3: segment
        segments = self._segmenter.segment(text)

        # Stage 4: per-segment processing
        seg_results: List[SegmentResult] = []
        failure_reasons: List[str] = []
        prepared_parts: List[str] = []
        html_parts: List[str] = []

        for seg in segments:
            sr = self._process_segment(seg, family_prior=family_prior, source_family=family)
            seg_results.append(sr)
            repairs_applied.extend(sr.repairs)
            if not sr.validation.ok:
                failure_reasons.extend(sr.validation.reasons)
            prepared_parts.append(sr.prepared)
            html_parts.append(sr.html)

        result = PipelineResult(
            prepared_text="".join(prepared_parts),
            html="".join(html_parts),
            segments=seg_results,
            repairs_applied=repairs_applied,
            failure_reasons=failure_reasons,
        )
        result.buckets = self._bucket_labeler.label(text, result)
        return result

    # ------------------------------------------------------------------
    # HTML-aware processing — tags pass through, math inside still renders

    def _run_html_aware(self, text: str, *, family: str, family_prior: float) -> PipelineResult:
        """Process a row that contains HTML tags. Splits on tag boundaries;
        whitelisted tags are emitted verbatim, everything else runs through
        the normal math pipeline.
        """
        # Walk the text, building (kind, slice) chunks.
        chunks: List[tuple[str, str]] = []   # [("html", "<table>"), ("prose", "Find ..."), ...]
        i = 0
        for m in _RE_HTML_TAG.finditer(text):
            if m.start() > i:
                chunks.append(("prose", text[i:m.start()]))
            tag_name = m.group(1).lower()
            if tag_name in _ALLOWED_HTML_TAGS:
                chunks.append(("html", m.group(0)))
            else:
                # Unknown tag — treat as literal text so KaTeX never sees it.
                chunks.append(("prose", m.group(0)))
            i = m.end()
        if i < len(text):
            chunks.append(("prose", text[i:]))

        prepared_parts: List[str] = []
        html_parts: List[str] = []
        seg_results: List[SegmentResult] = []
        repairs_applied: List[str] = []
        failure_reasons: List[str] = []

        for kind, chunk in chunks:
            if kind == "html":
                # Verbatim passthrough — the consumer renders this HTML.
                seg = SegmentResult(
                    kind=SegmentKind.HTML, original=chunk, repaired=chunk,
                    classification=ClassificationResult(score=0.0, signals={"html_tag": True},
                                                        is_html=True),
                    validation=ValidationResult(True, []),
                    outcome=RenderOutcome.HTML,
                    prepared=chunk, html=chunk,
                )
                seg_results.append(seg)
                prepared_parts.append(chunk)
                html_parts.append(chunk)
                continue

            # Prose chunk — run a mini pipeline. Tier-1 global, Tier-2 wrap,
            # segment, per-segment math/text processing.
            sub_text = chunk
            for r in self._tier1_global:
                o = r.repair(sub_text, family_prior=family_prior)
                sub_text = o.text
                repairs_applied.extend(o.applied)
            for r in self._tier2_global:
                o = r.repair(sub_text, family_prior=family_prior)
                sub_text = o.text
                repairs_applied.extend(o.applied)

            sub_segs = self._segmenter.segment(sub_text)
            for seg in sub_segs:
                sr = self._process_segment(seg, family_prior=family_prior, source_family=family)
                seg_results.append(sr)
                repairs_applied.extend(sr.repairs)
                if not sr.validation.ok:
                    failure_reasons.extend(sr.validation.reasons)
                prepared_parts.append(sr.prepared)
                html_parts.append(sr.html)

        result = PipelineResult(
            prepared_text="".join(prepared_parts),
            html="".join(html_parts),
            segments=seg_results,
            repairs_applied=repairs_applied,
            failure_reasons=failure_reasons,
        )
        result.buckets = self._bucket_labeler.label(text, result)
        return result

    # ------------------------------------------------------------------
    # Per-segment logic

    def _process_segment(self, seg: Segment, *, family_prior: float,
                         source_family: str) -> SegmentResult:
        if seg.kind is SegmentKind.TEXT:
            return self._process_prose(seg)

        return self._process_math(seg, family_prior=family_prior, source_family=source_family)

    def _process_prose(self, seg: Segment) -> SegmentResult:
        out = seg.content
        applied: List[str] = []
        for r in self._tier1_prose:
            o = r.repair(out)
            out = o.text
            applied.extend(o.applied)
        html = html_escape(out).replace("\n", "<br>")
        return SegmentResult(
            kind=seg.kind, original=seg.content, repaired=out,
            classification=ClassificationResult(score=0.0, signals={"prose": True}),
            repairs=applied, validation=ValidationResult(True, []),
            outcome=RenderOutcome.TEXT,
            prepared=out, html=html,
        )

    def _process_math(self, seg: Segment, *, family_prior: float,
                      source_family: str) -> SegmentResult:
        content = seg.content
        applied: List[str] = []

        # Initial classification (inside math delim)
        cls = self._classifier.classify(content,
                                        source_family=source_family,
                                        inside_math_delim=True)

        # Tier 1 math fixes (always)
        for r in self._tier1_math:
            o = r.repair(content, classification=cls, family_prior=family_prior)
            content = o.text
            applied.extend(o.applied)

        # If Tier 1 stripped the segment to whitespace (e.g. content was only
        # a combining diacritic that got removed), demote to a TEXT segment
        # containing the original delimited form so the user sees the source
        # text instead of a fallback. Better than crashing or showing a
        # red error span.
        if not content.strip():
            literal = self._wrap_delim(seg.kind, seg.content)
            return SegmentResult(
                kind=SegmentKind.TEXT, original=seg.content, repaired=content,
                classification=cls, repairs=applied,
                validation=ValidationResult(True, []),
                outcome=RenderOutcome.TEXT,
                prepared=literal,
                html=self._fallback.render(literal, reason="math_emptied_by_repair").replace(
                    'class="latex-fallback"', 'class="latex-fallback-soft"'
                ),
            )

        # Tier 2 math fixes if confidence or corruption signal warrants
        if cls.has_corruption or cls.score >= self._repair_threshold:
            for r in self._tier2_math:
                o = r.repair(content, classification=cls, family_prior=family_prior)
                content = o.text
                applied.extend(o.applied)

        # Re-classify after repair (validation-after-repair)
        cls2 = self._classifier.classify(content,
                                         source_family=source_family,
                                         inside_math_delim=True)

        validation = self._validator.validate(content)
        prepared = self._wrap_delim(seg.kind, content)

        if not validation.ok:
            html = self._fallback.render(prepared, reason=";".join(validation.reasons))
            return SegmentResult(
                kind=seg.kind, original=seg.content, repaired=content,
                classification=cls2, repairs=applied,
                validation=validation, outcome=RenderOutcome.FALLBACK,
                prepared=prepared, html=html,
            )

        placeholder = self._math_placeholder(seg.kind, prepared)
        return SegmentResult(
            kind=seg.kind, original=seg.content, repaired=content,
            classification=cls2, repairs=applied,
            validation=validation, outcome=RenderOutcome.MATH,
            prepared=prepared, html=placeholder,
        )

    # ------------------------------------------------------------------
    # Delimiter helpers

    @staticmethod
    def _wrap_delim(kind: SegmentKind, content: str) -> str:
        if kind is SegmentKind.MATH_DISPLAY:  return f"$${content}$$"
        if kind is SegmentKind.MATH_PAREN:    return f"\\({content}\\)"
        if kind is SegmentKind.MATH_BRACKET:  return f"\\[{content}\\]"
        return f"${content}$"

    @staticmethod
    def _math_placeholder(kind: SegmentKind, prepared: str) -> str:
        mode = "display" if kind.is_display else "inline"
        return f'<span class="latex-math" data-math="{mode}">{html_escape(prepared)}</span>'
