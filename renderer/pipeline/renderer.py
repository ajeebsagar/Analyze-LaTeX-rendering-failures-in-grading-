"""
End-to-end pipeline: Detect -> Classify -> Repair -> Validate -> Prepare -> Fallback.

The pipeline produces a PipelineResult containing:
  - `prepared_text`: a string safe to hand to KaTeX `renderToString` on either
    the browser or Node side. Each math span is delimited by `$...$` (inline)
    or `$$...$$` (display), so a KaTeX auto-render pass will pick them up.
  - `html`: an HTML string suitable for direct injection. For math segments it
    emits `<span data-math="inline">...</span>` placeholders; for failed
    segments it emits `<span class="latex-fallback">...</span>`. The actual
    KaTeX HTML is filled in client-side OR server-side via the optional
    `katex_render_fn` argument.
  - `segments`: per-segment result records.
  - `repairs_applied`: flat list for telemetry.
  - `failure_reasons`: flat list of validation rejection reasons.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .classifier import (
    ClassificationResult, SOURCE_MATH_PRIOR, classify, family_of,
)
from .fallback import fallback_span, html_escape
from .repair import (
    tier1_global, tier1_math_segment, tier1_prose_segment,
    tier2_orphan_backslash, tier2_wrap_math_only,
)
from .segmenter import Segment, segment
from .validator import validate

# Threshold above which we will attempt to render a candidate as math.
RENDER_CONFIDENCE_THRESHOLD = 0.55

# Threshold above which Tier 2 heuristic repairs are allowed to fire.
REPAIR_CONFIDENCE_THRESHOLD = 0.7


@dataclass
class SegmentResult:
    kind: str                # original segment kind from segmenter
    original: str            # original raw content (pre-repair)
    repaired: str            # post-repair content
    classification: ClassificationResult
    repairs: List[str] = field(default_factory=list)
    validation_ok: bool = True
    validation_reasons: List[str] = field(default_factory=list)
    prepared: str = ""       # KaTeX-ready string, e.g. "$\\frac{1}{2}$"
    html_placeholder: str = ""  # HTML placeholder span
    rendered_as: str = "text"   # "math" | "text" | "fallback"


@dataclass
class PipelineResult:
    prepared_text: str
    html: str
    segments: List[SegmentResult]
    repairs_applied: List[str]
    failure_reasons: List[str]


def prepare_text(
    text: str,
    *,
    field_path: Optional[str] = None,
    source_family: Optional[str] = None,
) -> PipelineResult:
    """
    Run the full pipeline on `text` and return a PipelineResult.

    `source_family` overrides the family inferred from `field_path`.
    """
    if text is None:
        text = ""

    fam = source_family or family_of(field_path)
    family_prior = SOURCE_MATH_PRIOR.get(fam, 0.3)

    # --- Stage 0: HTML short-circuit ---
    # If the input contains HTML tags, do not run math segmentation on it;
    # we pass the whole string through as one HTML-routed segment.
    from .classifier import _RE_HTML
    if _RE_HTML.search(text):
        seg_res = SegmentResult(
            kind="html",
            original=text,
            repaired=text,
            classification=ClassificationResult(
                score=0.0, is_math=False, signals={"html": True},
                corruption=False, is_html=True, is_currency=False, is_fill_blank=False,
            ),
            prepared=text,
            html_placeholder=fallback_span(text, reason="html_content"),
            rendered_as="fallback",
        )
        return PipelineResult(
            prepared_text=text, html=seg_res.html_placeholder,
            segments=[seg_res], repairs_applied=[], failure_reasons=["html_content"],
        )

    # --- Stage 1: global Tier 1 transforms ---
    text2, global_repairs = tier1_global(text)

    # --- Stage 2: tier2 whole-text wrap (only for math-only single-value fields) ---
    wrapped_text, wrap_repairs, was_wrapped = tier2_wrap_math_only(
        text2, family_prior=family_prior
    )
    text2 = wrapped_text

    repairs_applied: List[str] = list(global_repairs) + list(wrap_repairs)
    failure_reasons: List[str] = []

    # --- Stage 3: segment ---
    segs = segment(text2)

    out_html_parts: List[str] = []
    out_prepared_parts: List[str] = []
    seg_results: List[SegmentResult] = []

    for s in segs:
        sr = _process_segment(s, family_prior=family_prior)
        repairs_applied.extend(sr.repairs)
        if not sr.validation_ok:
            failure_reasons.extend(sr.validation_reasons)
        out_html_parts.append(sr.html_placeholder)
        out_prepared_parts.append(sr.prepared)
        seg_results.append(sr)

    return PipelineResult(
        prepared_text="".join(out_prepared_parts),
        html="".join(out_html_parts),
        segments=seg_results,
        repairs_applied=repairs_applied,
        failure_reasons=failure_reasons,
    )


def _process_segment(s: Segment, *, family_prior: float) -> SegmentResult:
    """Per-segment Tier 1/2 repair + validate + prepare."""
    if s.kind == "text":
        repaired, repairs = tier1_prose_segment(s.content)
        # Prose text is HTML-escaped; line breaks become <br>.
        html = html_escape(repaired).replace("\n", "<br>")
        return SegmentResult(
            kind=s.kind, original=s.content, repaired=repaired,
            classification=ClassificationResult(
                score=0.0, is_math=False, signals={"prose": True},
                corruption=False, is_html=False, is_currency=False, is_fill_blank=False,
            ),
            repairs=repairs,
            prepared=repaired,
            html_placeholder=html,
            rendered_as="text",
        )

    # Math segment ($..$, $$..$$, \(..\), \[..\])
    inside_math = True
    cls = classify(s.content, source_family="_inside_delim", inside_math_delim=inside_math)
    repairs: List[str] = []

    # Tier 1 math fixes
    content, r1 = tier1_math_segment(s.content)
    repairs.extend(r1)

    # Tier 2 repairs (gated on confidence)
    if cls.corruption or cls.score >= REPAIR_CONFIDENCE_THRESHOLD or inside_math:
        content, r2 = tier2_orphan_backslash(content)
        repairs.extend(r2)

    # Re-classify after repairs to update score
    cls2 = classify(content, source_family="_inside_delim", inside_math_delim=True)

    # Validate
    v = validate(content)
    if not v.ok:
        return SegmentResult(
            kind=s.kind, original=s.content, repaired=content,
            classification=cls2, repairs=repairs,
            validation_ok=False, validation_reasons=v.reasons,
            prepared=_re_delim(s.kind, content),  # still emit prepared for reference
            html_placeholder=fallback_span(_re_delim(s.kind, content),
                                           reason=";".join(v.reasons)),
            rendered_as="fallback",
        )

    prepared = _re_delim(s.kind, content)
    placeholder = _math_placeholder(s.kind, prepared)
    return SegmentResult(
        kind=s.kind, original=s.content, repaired=content,
        classification=cls2, repairs=repairs,
        prepared=prepared,
        html_placeholder=placeholder,
        rendered_as="math",
    )


def _re_delim(kind: str, content: str) -> str:
    if kind == "math_display":
        return f"$${content}$$"
    if kind == "math_paren":
        return f"\\({content}\\)"
    if kind == "math_bracket":
        return f"\\[{content}\\]"
    return f"${content}$"


def _math_placeholder(kind: str, prepared: str) -> str:
    mode = "display" if kind in ("math_display", "math_bracket") else "inline"
    return (
        f'<span class="latex-math" data-math="{mode}">'
        f'{html_escape(prepared)}</span>'
    )


# --- High-level helpers ---

def render_text(
    text: str,
    *,
    field_path: Optional[str] = None,
    source_family: Optional[str] = None,
    katex_render_fn: Optional[Callable[[str, bool], str]] = None,
) -> str:
    """
    Run the pipeline and return final HTML.

    If `katex_render_fn(latex, display) -> html` is provided (e.g. wired to
    Node's katex.renderToString), math placeholders are filled with rendered
    HTML. Otherwise the prepared `$...$` text is kept inside the span and the
    browser is expected to run KaTeX auto-render on `.latex-math` elements.
    """
    result = prepare_text(text, field_path=field_path, source_family=source_family)
    if katex_render_fn is None:
        return result.html

    out: List[str] = []
    for seg, sr in zip(_split_html(result.html), result.segments):
        if sr.rendered_as != "math":
            out.append(seg)
            continue
        is_display = sr.kind in ("math_display", "math_bracket")
        try:
            inner = katex_render_fn(sr.repaired, is_display)
            out.append(
                f'<span class="latex-math katex-rendered" data-math="'
                f'{"display" if is_display else "inline"}">{inner}</span>'
            )
        except Exception as exc:
            out.append(fallback_span(
                _re_delim(sr.kind, sr.repaired),
                reason=f"katex_error:{type(exc).__name__}",
            ))
    return "".join(out)


def _split_html(html: str) -> List[str]:
    # The HTML produced by `prepare_text` is a flat concatenation of segment
    # placeholders. Splitting on the placeholder boundary lets us reconstruct
    # per-segment HTML 1:1 with `result.segments`. This is a small helper used
    # only by `render_text` when a KaTeX render function is provided.
    import re as _re
    # Match either a fallback span, a math placeholder, or raw text up to the
    # next span boundary.
    parts: List[str] = []
    i = 0
    n = len(html)
    while i < n:
        if html.startswith("<span ", i):
            # find matching </span>
            j = html.find("</span>", i)
            if j == -1:
                parts.append(html[i:])
                break
            parts.append(html[i: j + len("</span>")])
            i = j + len("</span>")
        else:
            j = html.find("<span ", i)
            if j == -1:
                parts.append(html[i:])
                break
            parts.append(html[i:j])
            i = j
    return parts


def render_dataset_row(row: dict, **kwargs) -> PipelineResult:
    """Convenience for processing one row from the dataset JSONL/CSV."""
    return prepare_text(
        row.get("raw_text", "") or "",
        field_path=row.get("field_path"),
        **kwargs,
    )
