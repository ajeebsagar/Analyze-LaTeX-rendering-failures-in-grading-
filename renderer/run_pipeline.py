"""
CLI runner: process the dataset through the pipeline and emit:

  - results.jsonl   one record per input row (segment outcomes, repairs, etc.)
  - report.json     aggregate stats
  - report.md       human-readable report
  - demo.html       small HTML preview of the first --preview-count rows

Run:
  python run_pipeline.py --input ../classified_candidates.jsonl --limit 5000
  python run_pipeline.py --input ../confirmed_broken.csv --limit 1500
  python run_pipeline.py --input ../golden_test_set.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Iterator, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import prepare_text
from pipeline.classifier import family_of


def iter_rows(path: str) -> Iterator[dict]:
    """Yield dict rows from either JSONL or CSV input."""
    if path.endswith(".jsonl"):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
    elif path.endswith(".csv"):
        with open(path, "r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                yield row
    else:
        raise ValueError(f"Unsupported input: {path}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="path to .jsonl or .csv")
    ap.add_argument("--outdir", default="./out", help="output directory")
    ap.add_argument("--limit", type=int, default=None, help="cap rows for speed")
    ap.add_argument("--preview-count", type=int, default=40,
                    help="number of rows to include in demo.html")
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    results_path = os.path.join(args.outdir, "results.jsonl")
    report_json = os.path.join(args.outdir, "report.json")
    report_md = os.path.join(args.outdir, "report.md")
    demo_html = os.path.join(args.outdir, "demo.html")

    # Aggregates
    n_rows = 0
    n_with_any_fallback = 0
    n_with_any_math = 0
    n_with_repair = 0
    by_category_outcome = defaultdict(Counter)  # original_category -> outcome counter
    by_family_outcome = defaultdict(Counter)
    repair_counts = Counter()
    failure_reasons = Counter()
    seg_kind_counts = Counter()
    seg_outcome_counts = Counter()

    preview_rows = []

    t0 = time.time()
    with open(results_path, "w", encoding="utf-8") as out:
        for row in iter_rows(args.input):
            if args.limit is not None and n_rows >= args.limit:
                break
            n_rows += 1

            raw = row.get("raw_text", "") or ""
            field_path = row.get("field_path")
            original_category = row.get("category", "unknown")
            fam = family_of(field_path)

            try:
                result = prepare_text(raw, field_path=field_path)
                pipeline_error = None
            except Exception as exc:
                # The pipeline itself must not throw. If it does, that is a bug.
                pipeline_error = f"{type(exc).__name__}: {exc}"
                result = None

            had_fallback = False
            had_math = False
            seg_dicts = []
            if result is not None:
                for s in result.segments:
                    seg_kind_counts[s.kind] += 1
                    seg_outcome_counts[s.rendered_as] += 1
                    if s.rendered_as == "fallback":
                        had_fallback = True
                    if s.rendered_as == "math":
                        had_math = True
                    seg_dicts.append({
                        "kind": s.kind,
                        "outcome": s.rendered_as,
                        "score": round(s.classification.score, 3),
                        "signals": s.classification.signals,
                        "repairs": s.repairs,
                        "validation_reasons": s.validation_reasons,
                        "original_len": len(s.original),
                        "repaired_len": len(s.repaired),
                    })
                for r in result.repairs_applied:
                    repair_counts[r] += 1
                for f in result.failure_reasons:
                    failure_reasons[f] += 1

            if had_fallback:
                n_with_any_fallback += 1
            if had_math:
                n_with_any_math += 1
            if result and result.repairs_applied:
                n_with_repair += 1

            outcome_key = "ok" if (not had_fallback and pipeline_error is None) else (
                "pipeline_error" if pipeline_error else "fallback"
            )
            by_category_outcome[original_category][outcome_key] += 1
            by_family_outcome[fam][outcome_key] += 1

            record = {
                "dataset_row_id": row.get("dataset_row_id"),
                "category": original_category,
                "family": fam,
                "ui_surface": row.get("ui_surface"),
                "had_math": had_math,
                "had_fallback": had_fallback,
                "pipeline_error": pipeline_error,
                "segments": seg_dicts,
                "prepared_text": result.prepared_text if result else None,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

            if len(preview_rows) < args.preview_count and (had_math or had_fallback):
                preview_rows.append({
                    "raw": raw,
                    "html": result.html if result else "",
                    "prepared": result.prepared_text if result else "",
                    "category": original_category,
                    "field_path": field_path,
                    "repairs": result.repairs_applied if result else [],
                    "outcome": outcome_key,
                })

    elapsed = time.time() - t0

    report = {
        "input": args.input,
        "n_rows": n_rows,
        "elapsed_seconds": round(elapsed, 2),
        "rows_per_sec": round(n_rows / elapsed, 1) if elapsed > 0 else None,
        "n_with_any_math": n_with_any_math,
        "n_with_any_fallback": n_with_any_fallback,
        "n_with_repair_applied": n_with_repair,
        "fallback_rate": round(n_with_any_fallback / n_rows, 4) if n_rows else 0,
        "repair_rate": round(n_with_repair / n_rows, 4) if n_rows else 0,
        "seg_kind_counts": dict(seg_kind_counts.most_common()),
        "seg_outcome_counts": dict(seg_outcome_counts.most_common()),
        "repair_counts": dict(repair_counts.most_common()),
        "failure_reason_counts": dict(failure_reasons.most_common()),
        "by_category_outcome": {k: dict(v) for k, v in by_category_outcome.items()},
        "by_family_outcome": {k: dict(v) for k, v in by_family_outcome.items()},
    }
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    _write_md_report(report_md, report)
    _write_demo_html(demo_html, preview_rows)

    print(f"Processed {n_rows} rows in {elapsed:.2f}s ({report['rows_per_sec']} rows/s).")
    print(f"Results:   {results_path}")
    print(f"Report:    {report_md}")
    print(f"Demo HTML: {demo_html}")


def _write_md_report(path: str, report: dict) -> None:
    lines = []
    lines.append("# Pipeline Run Report\n")
    lines.append(f"- Input: `{report['input']}`")
    lines.append(f"- Rows processed: **{report['n_rows']}**")
    lines.append(f"- Elapsed: {report['elapsed_seconds']}s ({report['rows_per_sec']} rows/s)")
    lines.append(f"- Rows with any math: {report['n_with_any_math']}")
    lines.append(f"- Rows with any fallback: {report['n_with_any_fallback']} "
                 f"({report['fallback_rate']*100:.2f}%)")
    lines.append(f"- Rows where any repair was applied: {report['n_with_repair_applied']} "
                 f"({report['repair_rate']*100:.2f}%)")
    lines.append("")
    lines.append("## Segment outcomes\n")
    for k, v in report["seg_outcome_counts"].items():
        lines.append(f"- {k}: {v}")
    lines.append("\n## Top repairs applied\n")
    for k, v in list(report["repair_counts"].items())[:20]:
        lines.append(f"- {k}: {v}")
    lines.append("\n## Top validation rejection reasons\n")
    for k, v in list(report["failure_reason_counts"].items())[:20]:
        lines.append(f"- {k}: {v}")
    lines.append("\n## Outcome by original category\n")
    for cat, oc in report["by_category_outcome"].items():
        total = sum(oc.values())
        ok = oc.get("ok", 0); fb = oc.get("fallback", 0); pe = oc.get("pipeline_error", 0)
        lines.append(f"- **{cat}** (n={total}): ok={ok} ({ok*100/total:.1f}%), "
                     f"fallback={fb} ({fb*100/total:.1f}%), pipeline_error={pe}")
    lines.append("\n## Outcome by source family\n")
    for fam, oc in report["by_family_outcome"].items():
        total = sum(oc.values())
        ok = oc.get("ok", 0); fb = oc.get("fallback", 0); pe = oc.get("pipeline_error", 0)
        lines.append(f"- **{fam}** (n={total}): ok={ok} ({ok*100/total:.1f}%), "
                     f"fallback={fb} ({fb*100/total:.1f}%), pipeline_error={pe}")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


def _write_demo_html(path: str, rows: list) -> None:
    head = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"/>
<title>LaTeX Renderer Demo</title>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css">
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"
    onload="renderMathInElement(document.body,{
      delimiters:[
        {left:'$$',right:'$$',display:true},
        {left:'$', right:'$', display:false},
        {left:'\\\\[',right:'\\\\]',display:true},
        {left:'\\\\(',right:'\\\\)',display:false}
      ],
      throwOnError:false,
      strict:'ignore'
    });"></script>
<style>
  body{font-family:system-ui,sans-serif;max-width:880px;margin:24px auto;padding:0 16px;line-height:1.5}
  .row{border:1px solid #ddd;border-radius:8px;padding:12px;margin:12px 0;background:#fafafa}
  .meta{font-size:12px;color:#666;margin-bottom:8px;display:flex;gap:12px;flex-wrap:wrap}
  .meta code{background:#eee;padding:2px 4px;border-radius:3px}
  .raw{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12px;color:#555;
       background:#f3f3f3;padding:8px;border-radius:6px;white-space:pre-wrap;word-break:break-word;margin:8px 0}
  .rendered{padding:8px;background:white;border-radius:6px;border:1px solid #eee}
  .latex-fallback{background:#fff3cd;color:#7a5b00;padding:0 2px;border-radius:3px;font-family:monospace}
  .badge{display:inline-block;padding:1px 6px;border-radius:10px;font-size:11px;background:#eef;color:#225}
  .badge.fallback{background:#fde2e2;color:#7a1f1f}
  .badge.ok{background:#dff5dc;color:#1b5e20}
</style>
</head>
<body>
<h1>LaTeX Renderer — Live Demo (KaTeX auto-render)</h1>
<p>Each row shows the original raw text from the dataset, followed by the
pipeline-prepared HTML. KaTeX auto-render runs on the rendered block.</p>
"""
    parts = [head]
    for row in rows:
        outcome_class = "fallback" if row["outcome"] == "fallback" else (
            "ok" if row["outcome"] == "ok" else "fallback"
        )
        parts.append('<div class="row">')
        parts.append('<div class="meta">')
        parts.append(f'<span class="badge {outcome_class}">{row["outcome"]}</span>')
        parts.append(f'<code>{row["category"]}</code>')
        if row["field_path"]:
            parts.append(f'<code>{row["field_path"]}</code>')
        if row["repairs"]:
            parts.append(f'<code>repairs: {", ".join(row["repairs"])}</code>')
        parts.append('</div>')
        parts.append(f'<div class="raw">{_html_escape(row["raw"])}</div>')
        parts.append(f'<div class="rendered">{row["html"]}</div>')
        parts.append('</div>')
    parts.append("</body></html>")
    with open(path, "w", encoding="utf-8") as f:
        f.write("".join(parts))


def _html_escape(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;").replace("'", "&#39;"))


if __name__ == "__main__":
    main()
