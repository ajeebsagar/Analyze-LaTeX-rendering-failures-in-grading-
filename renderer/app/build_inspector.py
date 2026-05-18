"""Build the observability inspector data.

Reads the original dataset (JSONL or CSV), takes a STRATIFIED SAMPLE across
buckets / source families / dataset categories, runs each sampled row
through the SOLID pipeline, and writes `web/inspector/data.json` with the
complete trace.

Usage:
  python -m app.build_inspector --input ../classified_candidates.jsonl
  python -m app.build_inspector --input ../confirmed_broken.csv --per-stratum 60
"""
from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import random
import sys
from collections import Counter, defaultdict
from typing import Dict, Iterator, List

_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(os.path.dirname(_here), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from latex_pipeline import build_default_pipeline, RenderOutcome, BUCKET_DESCRIPTIONS
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


def stratified_sample(
    rows: List[dict],
    *,
    per_stratum: int,
    keys: List[str],
    rng: random.Random,
) -> List[dict]:
    """Return a sample where each value of each `keys` column has at most
    `per_stratum` representatives. Combined across multiple keys via union.
    """
    chosen: Dict[str, dict] = {}
    by_key: Dict[tuple, List[dict]] = defaultdict(list)
    for r in rows:
        for k in keys:
            v = r.get(k) or "_"
            by_key[(k, v)].append(r)

    for (_, _), pool in by_key.items():
        rng.shuffle(pool)
        for r in pool[:per_stratum]:
            chosen[r["dataset_row_id"]] = r
    out = list(chosen.values())
    rng.shuffle(out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True,
                    help="path to dataset (jsonl or csv)")
    ap.add_argument("--output", default=None,
                    help="path to write data.json (default web/inspector/data.json)")
    ap.add_argument("--per-stratum", type=int, default=40,
                    help="max rows per (category|family|ui_surface) value (default 40)")
    ap.add_argument("--max-rows", type=int, default=1500,
                    help="hard cap on final sample size (default 1500)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    rng = random.Random(args.seed)

    print(f"Loading rows from {args.input} ...")
    all_rows = []
    for row in iter_rows(args.input):
        # Ensure dataset_row_id exists (CSV always has it; JSONL too)
        if "dataset_row_id" not in row:
            row["dataset_row_id"] = f"row-{len(all_rows)}"
        all_rows.append(row)
    print(f"  Loaded {len(all_rows):,} rows.")

    # Stratify across category + family + ui_surface so the sample covers
    # every visible facet of the dataset.
    resolver = DefaultFamilyResolver()
    for r in all_rows:
        r["_family"] = resolver.family_of(r.get("field_path"))

    sampled = stratified_sample(
        all_rows,
        per_stratum=args.per_stratum,
        keys=["category", "_family", "ui_surface", "tenant"],
        rng=rng,
    )
    if len(sampled) > args.max_rows:
        sampled = sampled[: args.max_rows]
    print(f"  Sampled {len(sampled):,} rows after stratification + cap.")

    # Run pipeline
    pipeline = build_default_pipeline()
    out_rows = []
    bucket_counts = Counter()
    family_counts = Counter()
    category_counts = Counter()
    repair_counts = Counter()
    outcome_counts = Counter()
    surface_counts = Counter()
    tenant_counts = Counter()
    n_math = n_fb = n_repair = 0

    print("Running pipeline on sample ...")
    for r in sampled:
        raw = r.get("raw_text") or ""
        result = pipeline.run(raw, field_path=r.get("field_path"))

        had_math = any(s.outcome is RenderOutcome.MATH for s in result.segments)
        had_fb = any(s.outcome is RenderOutcome.FALLBACK for s in result.segments)
        outcome = "fallback" if had_fb else ("math" if had_math else "text")
        outcome_counts[outcome] += 1
        if had_math: n_math += 1
        if had_fb: n_fb += 1
        if result.repairs_applied: n_repair += 1

        for b in result.buckets:
            bucket_counts[b] += 1
        for rp in result.repairs_applied:
            repair_counts[rp] += 1
        family_counts[r["_family"]] += 1
        category_counts[r.get("category", "unknown")] += 1
        surface_counts[r.get("ui_surface", "unknown")] += 1
        tenant_counts[r.get("tenant", "unknown")] += 1

        out_rows.append({
            "id": r.get("dataset_row_id"),
            "tenant": r.get("tenant"),
            "category": r.get("category"),
            "family": r["_family"],
            "ui_surface": r.get("ui_surface"),
            "field_path": r.get("field_path"),
            "subject": r.get("subject_name"),
            "grade": r.get("grade_name"),
            "raw": raw,
            "prepared": result.prepared_text,
            "html": result.html,
            "buckets": result.buckets,
            "outcome": outcome,
            "had_math": had_math,
            "had_fallback": had_fb,
            "repairs": result.repairs_applied,
            "failure_reasons": result.failure_reasons,
            "segments": [
                {
                    "kind": s.kind.value,
                    "outcome": s.outcome.value,
                    "score": round(s.classification.score, 3),
                    "signals": s.classification.signals,
                    "original": s.original,
                    "repaired": s.repaired,
                    "repairs": s.repairs,
                    "validation_ok": s.validation.ok,
                    "validation_reasons": s.validation.reasons,
                    "prepared": s.prepared,
                }
                for s in result.segments
            ],
        })

    data = {
        "meta": {
            "input_path": args.input,
            "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "total_input_rows": len(all_rows),
            "sampled_rows": len(out_rows),
            "summary": {
                "n_math": n_math,
                "n_fallback": n_fb,
                "n_repair": n_repair,
                "outcome_counts": dict(outcome_counts),
                "bucket_counts": dict(bucket_counts.most_common()),
                "bucket_descriptions": BUCKET_DESCRIPTIONS,
                "repair_counts": dict(repair_counts.most_common()),
                "family_counts": dict(family_counts.most_common()),
                "category_counts": dict(category_counts.most_common()),
                "ui_surface_counts": dict(surface_counts.most_common()),
                "tenant_counts": dict(tenant_counts.most_common()),
            },
        },
        "rows": out_rows,
    }

    out_path = args.output or os.path.join(
        os.path.dirname(_here), "web", "inspector", "data.json"
    )
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    sz = os.path.getsize(out_path)
    print(f"Wrote {out_path} ({sz/1024:.1f} KB, {len(out_rows)} rows).")
    print(f"  math={n_math}  fallback={n_fb}  repair={n_repair}")


if __name__ == "__main__":
    main()
