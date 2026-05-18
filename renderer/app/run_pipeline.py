"""Dataset CLI for the SOLID pipeline.

Usage:
  python -m app.run_pipeline --input ../golden_test_set.csv --outdir out/golden_solid
  python -m app.run_pipeline --input ../classified_candidates.jsonl --outdir out/full_solid
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from collections import Counter, defaultdict
from typing import Iterator

_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(os.path.dirname(_here), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from latex_pipeline import build_default_pipeline, RenderOutcome
from latex_pipeline.classification import DefaultFamilyResolver


def iter_rows(path: str) -> Iterator[dict]:
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
    ap.add_argument("--input", required=True)
    ap.add_argument("--outdir", default="./out_solid")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    results_path = os.path.join(args.outdir, "results.jsonl")
    report_json = os.path.join(args.outdir, "report.json")
    report_md = os.path.join(args.outdir, "report.md")

    pipeline = build_default_pipeline()
    resolver = DefaultFamilyResolver()

    n_rows = 0
    n_fallback = 0
    n_math = 0
    n_repair = 0
    n_errors = 0
    repair_counts = Counter()
    failure_reasons = Counter()
    bucket_counts = Counter()
    by_category_outcome = defaultdict(Counter)
    by_family_outcome = defaultdict(Counter)

    t0 = time.time()
    with open(results_path, "w", encoding="utf-8") as out:
        for row in iter_rows(args.input):
            if args.limit is not None and n_rows >= args.limit:
                break
            n_rows += 1

            raw = row.get("raw_text", "") or ""
            field_path = row.get("field_path")
            cat = row.get("category", "unknown")
            fam = resolver.family_of(field_path)

            try:
                result = pipeline.run(raw, field_path=field_path)
                pipeline_error = None
            except Exception as exc:
                pipeline_error = f"{type(exc).__name__}: {exc}"
                result = None
                n_errors += 1

            had_fb = had_math = False
            seg_dicts = []
            if result is not None:
                for s in result.segments:
                    if s.outcome is RenderOutcome.FALLBACK:
                        had_fb = True
                    if s.outcome is RenderOutcome.MATH:
                        had_math = True
                    seg_dicts.append({
                        "kind": s.kind.value,
                        "outcome": s.outcome.value,
                        "score": round(s.classification.score, 3),
                        "repairs": s.repairs,
                        "validation_reasons": s.validation.reasons,
                    })
                for r in result.repairs_applied:
                    repair_counts[r] += 1
                for f in result.failure_reasons:
                    failure_reasons[f] += 1
                for b in result.buckets:
                    bucket_counts[b] += 1

            if had_fb: n_fallback += 1
            if had_math: n_math += 1
            if result and result.repairs_applied: n_repair += 1

            outcome_key = ("pipeline_error" if pipeline_error else
                           "fallback" if had_fb else "ok")
            by_category_outcome[cat][outcome_key] += 1
            by_family_outcome[fam][outcome_key] += 1

            record = {
                "dataset_row_id": row.get("dataset_row_id"),
                "category": cat, "family": fam,
                "ui_surface": row.get("ui_surface"),
                "buckets": result.buckets if result else [],
                "had_math": had_math, "had_fallback": had_fb,
                "pipeline_error": pipeline_error,
                "segments": seg_dicts,
                "prepared_text": result.prepared_text if result else None,
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")

    elapsed = time.time() - t0
    report = {
        "input": args.input,
        "n_rows": n_rows,
        "elapsed_seconds": round(elapsed, 2),
        "rows_per_sec": round(n_rows / elapsed, 1) if elapsed > 0 else None,
        "n_with_any_math": n_math,
        "n_with_any_fallback": n_fallback,
        "n_pipeline_errors": n_errors,
        "n_with_repair_applied": n_repair,
        "fallback_rate": round(n_fallback / n_rows, 4) if n_rows else 0,
        "repair_rate": round(n_repair / n_rows, 4) if n_rows else 0,
        "repair_counts": dict(repair_counts.most_common()),
        "failure_reason_counts": dict(failure_reasons.most_common()),
        "bucket_counts": dict(bucket_counts.most_common()),
        "by_category_outcome": {k: dict(v) for k, v in by_category_outcome.items()},
        "by_family_outcome": {k: dict(v) for k, v in by_family_outcome.items()},
    }
    with open(report_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with open(report_md, "w", encoding="utf-8") as f:
        f.write(f"# SOLID Pipeline Run Report\n\n")
        f.write(f"- Input: `{args.input}`\n")
        f.write(f"- Rows: **{n_rows}**\n")
        f.write(f"- Elapsed: {elapsed:.2f}s ({report['rows_per_sec']} rows/s)\n")
        f.write(f"- Math rows: {n_math}\n")
        f.write(f"- Fallback rows: {n_fallback} ({report['fallback_rate']*100:.3f}%)\n")
        f.write(f"- Repair-applied rows: {n_repair} ({report['repair_rate']*100:.2f}%)\n")
        f.write(f"- Pipeline exceptions: **{n_errors}**\n\n")
        f.write("## Buckets matched\n")
        for k, v in report["bucket_counts"].items():
            f.write(f"- {k}: {v}\n")
        f.write("\n## Repairs applied\n")
        for k, v in report["repair_counts"].items():
            f.write(f"- {k}: {v}\n")

    print(f"Processed {n_rows} rows in {elapsed:.2f}s ({report['rows_per_sec']} rows/s).")
    print(f"Pipeline errors: {n_errors}")
    print(f"Fallback rate:   {report['fallback_rate']*100:.3f}%")
    print(f"Results:  {results_path}")
    print(f"Report:   {report_md}")


if __name__ == "__main__":
    main()
