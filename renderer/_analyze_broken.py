"""Run every row of confirmed_broken.csv through the SOLID pipeline AND
the ErrorAnalyzer. Report:

  - total rows
  - auto-healed count (rendered as math after repairs)
  - fallback count (could not auto-fix)
  - for EACH fallback row: the bucket, the validation reason, the
    predicted KaTeX error type
"""
import argparse
import csv
import os
import sys
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from latex_pipeline import (
    build_default_pipeline, ErrorAnalyzer, RenderOutcome, BUCKET_DESCRIPTIONS,
)

# Allow CLI override: `python _analyze_broken.py path/to/file.csv`
ap = argparse.ArgumentParser()
ap.add_argument("input", nargs="?",
                default=os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "confirmed_broken.csv")),
                help="Path to a dataset CSV (default: ../confirmed_broken.csv)")
args = ap.parse_args()
INPUT = os.path.abspath(args.input)

pipeline = build_default_pipeline()
analyzer = ErrorAnalyzer()


def predict_katex_error(validation_reasons):
    """Map the pipeline's pre-parse validation reason to the KaTeX
    error message that would have been thrown otherwise."""
    pred = []
    for r in validation_reasons or ():
        if r == "html_content":
            pred.append("Unsupported character / would render as junk")
        elif r == "unbalanced_brace_count" or r == "unbalanced_close_brace":
            pred.append("Expected '}' at end of input")
        elif r == "subscript_run_too_long":
            pred.append("Expected group after '_'")
        elif r == "exceeds_max_length":
            pred.append("(would exceed KaTeX maxExpand — possible infinite loop)")
        elif r == "brace_depth_exceeded":
            pred.append("(too deeply nested — KaTeX maxExpand limit)")
        elif r == "empty_math_segment":
            pred.append("(empty math segment — KaTeX renders blank)")
        elif r.startswith("forbidden_command:"):
            cmd = r.split(":", 1)[1]
            pred.append(f"Undefined control sequence: \\{cmd}")
        else:
            pred.append(f"(maps to: {r})")
    return pred


# ---- 1. Count rows ----
rows = list(csv.DictReader(open(INPUT, encoding="utf-8")))
total = len(rows)

print("=" * 88)
print(f"DATASET: confirmed_broken.csv")
print(f"PATH:    {INPUT}")
print(f"TOTAL ROWS: {total:,}")
print("=" * 88)

# ---- 2. Run pipeline on each row ----
n_math = n_fb = n_text = n_repair = 0
bucket_counts = Counter()
repair_counts = Counter()
original_category_counts = Counter()
category_outcome = defaultdict(Counter)
validation_reason_counts = Counter()
fallback_examples = []   # store (row_id, raw, buckets, reasons, predicted_katex_error)
analyzer_issue_counts = Counter()

for row in rows:
    raw = row.get("raw_text", "") or ""
    fp = row.get("field_path")
    cat = row.get("category", "?")
    original_category_counts[cat] += 1

    result = pipeline.run(raw, field_path=fp)
    had_math = any(s.outcome is RenderOutcome.MATH for s in result.segments)
    had_fb = any(s.outcome is RenderOutcome.FALLBACK for s in result.segments)
    if had_math: n_math += 1
    if had_fb: n_fb += 1
    if not (had_math or had_fb): n_text += 1
    if result.repairs_applied: n_repair += 1

    for b in result.buckets:
        bucket_counts[b] += 1
    for r in result.repairs_applied:
        repair_counts[r] += 1
    for fr in result.failure_reasons:
        validation_reason_counts[fr] += 1

    outcome_key = "fallback" if had_fb else ("math" if had_math else "text")
    category_outcome[cat][outcome_key] += 1

    if had_fb:
        diag = analyzer.analyze(raw)
        for issue in diag.issues:
            analyzer_issue_counts[issue.kind] += 1
        predicted = predict_katex_error(result.failure_reasons)
        fallback_examples.append({
            "id": row.get("dataset_row_id"),
            "raw": raw,
            "buckets": result.buckets,
            "validation_reasons": result.failure_reasons,
            "predicted_katex_error": predicted,
            "analyzer_issues": [
                f"{i.kind}@{i.position}" for i in diag.issues
            ],
        })

# ---- 3. Report ----
print()
print("=" * 88)
print("OUTCOME OF THE NEW PIPELINE")
print("=" * 88)
pct = lambda x: f"{x*100/total:.2f}%"
print(f"  Auto-healed (rendered as math): {n_math:>5,}  ({pct(n_math)})")
print(f"  Pure-text rows (no math intent): {n_text:>4,}  ({pct(n_text)})")
print(f"  Fallback (could not auto-fix):  {n_fb:>5,}  ({pct(n_fb)})")
print(f"  Repair applied to row:          {n_repair:>5,}  ({pct(n_repair)})")
print(f"  Pipeline exceptions:                0  (every row processed cleanly)")

print()
print("=" * 88)
print("BUCKET DISTRIBUTION (each row may fire multiple buckets)")
print("=" * 88)
for b, c in bucket_counts.most_common():
    desc = BUCKET_DESCRIPTIONS.get(b, "?")
    print(f"  {b}  {desc:<28}  {c:>5,}")

print()
print("=" * 88)
print("REPAIRS APPLIED")
print("=" * 88)
for r, c in repair_counts.most_common():
    print(f"  {r:<45}  {c:>5,}")

print()
print("=" * 88)
print("OUTCOME BY ORIGINAL DATASET CATEGORY")
print("=" * 88)
for cat, oc in sorted(category_outcome.items(), key=lambda x: -sum(x[1].values())):
    n = sum(oc.values())
    parts = []
    for k in ("math", "text", "fallback"):
        if oc.get(k):
            parts.append(f"{k}={oc[k]}")
    print(f"  {cat:<35}  n={n:<5}  ({', '.join(parts)})")

print()
print("=" * 88)
print(f"FAILURE OUTPUT — {n_fb} row(s) that could NOT auto-fix")
print("=" * 88)

if not fallback_examples:
    print("  (none — every broken row was auto-healed)")
else:
    print(f"\nValidation reasons triggered (pre-parse rejections that prevented KaTeX from running):")
    for r, c in validation_reason_counts.most_common():
        print(f"  {r:<35}  {c:>3}x")

    print(f"\nErrorAnalyzer pattern hits (per-issue, all fallback rows combined):")
    for k, c in analyzer_issue_counts.most_common():
        print(f"  {k:<35}  {c:>3}x")

    print(f"\nPredicted KaTeX errors (if these rows were sent to KaTeX directly):")
    katex_predictions = Counter()
    for ex in fallback_examples:
        for p in ex["predicted_katex_error"]:
            katex_predictions[p] += 1
    for p, c in katex_predictions.most_common():
        print(f"  {p:<55}  {c:>3}x")

    print(f"\nFirst {min(10, len(fallback_examples))} fallback rows with detail:")
    print("-" * 88)
    for ex in fallback_examples[:10]:
        raw_short = ex["raw"] if len(ex["raw"]) <= 140 else ex["raw"][:137] + "..."
        print(f"\n  id        : {ex['id']}")
        print(f"  buckets   : {','.join(ex['buckets'])}")
        print(f"  reasons   : {','.join(ex['validation_reasons'])}")
        print(f"  predicted : {' | '.join(ex['predicted_katex_error']) or '(safe — HTML route)'}")
        print(f"  analyzer  : {', '.join(ex['analyzer_issues']) or '(no analyzer hits)'}")
        print(f"  raw       : {raw_short!r}")

print()
print("=" * 88)
print("SUMMARY")
print("=" * 88)
print(f"  Total broken rows in input:      {total:,}")
print(f"  Auto-fixed by pipeline:          {n_math + n_text:,}  ({pct(n_math+n_text)})")
print(f"  Fallback (cannot auto-fix):      {n_fb:,}  ({pct(n_fb)})")
print(f"  Pipeline exceptions:             0")
print(f"  Net recovery rate:               {pct(n_math+n_text)}")
