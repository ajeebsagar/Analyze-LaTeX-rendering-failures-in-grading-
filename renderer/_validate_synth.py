"""Run the SOLID pipeline on _synth_dataset.jsonl and measure accuracy
PER FIELD per row. Identify overfitting: cases where the pipeline misbehaves
because the input shape differs from the original corpus.

Reports:
  - overall accuracy (rows that fully match expected)
  - per-bucket precision / recall
  - per-repair precision / recall
  - the failing rows themselves (so we can see WHERE overfitting hides)
"""
import os, sys, json
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path: sys.path.insert(0, _src)

from latex_pipeline import build_default_pipeline, RenderOutcome

INPUT = os.path.join(os.path.dirname(__file__), "_synth_dataset.jsonl")
pipeline = build_default_pipeline()

# Per-row pass/fail
pass_full = 0
fail_full = 0
failures = []   # detailed list

# Counters
expected_bucket_total = Counter()
matched_bucket_count = Counter()   # bucket appears in BOTH expected and actual
expected_repair_total = Counter()
matched_repair_count = Counter()

actual_bucket_total = Counter()   # how often each bucket fires in practice
actual_repair_total = Counter()

# Confusion: row_id -> (expected, actual)
outcome_confusion = defaultdict(lambda: defaultdict(int))

with open(INPUT, encoding="utf-8") as f:
    rows = [json.loads(line) for line in f if line.strip()]

print(f"Running pipeline on {len(rows):,} synthetic rows...")
for row in rows:
    res = pipeline.run(row["raw"], source_family=row["source_family"])

    # ----- 1. Outcome check (math / text / fallback) -----
    # HTML segments count as "text" (they pass through verbatim) so a row
    # with only HTML + prose maps to `text` outcome.
    if any(s.outcome is RenderOutcome.FALLBACK for s in res.segments):
        actual_outcome = "fallback"
    elif any(s.outcome is RenderOutcome.MATH for s in res.segments):
        actual_outcome = "math"
    else:
        actual_outcome = "text"
    expected_outcome = row["expected_outcome"]
    outcome_ok = (actual_outcome == expected_outcome)
    outcome_confusion[expected_outcome][actual_outcome] += 1

    # ----- 2. Bucket check (at least one expected bucket fired) -----
    actual_buckets = set(res.buckets)
    for b in row["expected_buckets"]:
        expected_bucket_total[b] += 1
        if b in actual_buckets:
            matched_bucket_count[b] += 1
    for b in actual_buckets:
        actual_bucket_total[b] += 1

    bucket_ok = any(b in actual_buckets for b in row["expected_buckets"])

    # ----- 3. Repair check -----
    actual_repairs = set(res.repairs_applied)
    for r in actual_repairs:
        actual_repair_total[r] += 1
    repairs_required_ok = all(r in actual_repairs for r in row["expected_repairs"])
    for r in row["expected_repairs"]:
        expected_repair_total[r] += 1
        if r in actual_repairs:
            matched_repair_count[r] += 1
    repairs_forbidden_ok = not any(r in actual_repairs for r in row["expected_no_repairs"])

    # ----- 4. Exact prepared_text check (when expected) -----
    prepared_ok = True
    if row.get("expected_prepared") is not None:
        prepared_ok = (res.prepared_text == row["expected_prepared"])

    full_ok = outcome_ok and bucket_ok and repairs_required_ok and repairs_forbidden_ok and prepared_ok
    if full_ok:
        pass_full += 1
    else:
        fail_full += 1
        failures.append({
            "id": row["id"], "raw": row["raw"], "family": row["source_family"],
            "expected_outcome": expected_outcome, "actual_outcome": actual_outcome,
            "expected_buckets": row["expected_buckets"], "actual_buckets": list(actual_buckets),
            "expected_repairs": row["expected_repairs"], "actual_repairs": list(actual_repairs),
            "expected_no_repairs": row["expected_no_repairs"],
            "expected_prepared": row.get("expected_prepared"),
            "actual_prepared": res.prepared_text,
            "outcome_ok": outcome_ok, "bucket_ok": bucket_ok,
            "repairs_required_ok": repairs_required_ok,
            "repairs_forbidden_ok": repairs_forbidden_ok,
            "prepared_ok": prepared_ok,
        })

n = len(rows)
print()
print("=" * 88)
print("OVERALL RESULTS")
print("=" * 88)
print(f"  Rows that fully match expected:  {pass_full:,}  ({pass_full*100/n:.2f}%)")
print(f"  Rows that fail at least one check:  {fail_full:,}  ({fail_full*100/n:.2f}%)")

# ----- Outcome confusion matrix -----
print()
print("OUTCOME CONFUSION (rows: expected, cols: actual)")
all_outcomes = ["math", "text", "fallback"]
print(f"           {''.join(f'{o:>10}' for o in all_outcomes)}")
for e in all_outcomes:
    row_str = f"  {e:<7}"
    for a in all_outcomes:
        n_cell = outcome_confusion[e][a]
        row_str += f"{n_cell:>10}"
    print(row_str)

# ----- Per-bucket recall -----
print()
print("PER-BUCKET RECALL (expected buckets that the pipeline correctly identified)")
print(f"  {'bucket':<7} {'expected':>10} {'matched':>10} {'recall':>10}")
for b in sorted(expected_bucket_total, key=lambda x: -expected_bucket_total[x]):
    exp = expected_bucket_total[b]
    mat = matched_bucket_count[b]
    rec = mat / exp if exp else 0
    print(f"  {b:<7} {exp:>10} {mat:>10} {rec*100:>9.2f}%")

# ----- Per-repair recall (when the test row expected a repair) -----
print()
print("PER-REPAIR RECALL (rows that expected the repair → repair actually fired)")
print(f"  {'repair':<45} {'expected':>10} {'matched':>10} {'recall':>8}")
for r in sorted(expected_repair_total, key=lambda x: -expected_repair_total[x]):
    exp = expected_repair_total[r]
    mat = matched_repair_count[r]
    rec = mat / exp if exp else 0
    print(f"  {r:<45} {exp:>10} {mat:>10} {rec*100:>7.2f}%")

# ----- Top failures (show first 15) -----
print()
print("=" * 88)
print(f"DETAILED FAILURE INSPECTION (first 15 of {len(failures)} failing rows)")
print("=" * 88)
for fail in failures[:15]:
    print()
    print(f"  id        : {fail['id']}")
    print(f"  family    : {fail['family']}")
    raw = fail['raw'] if len(fail['raw']) <= 90 else fail['raw'][:87] + '...'
    print(f"  raw       : {raw!r}")
    if not fail["outcome_ok"]:
        print(f"  OUTCOME   : expected={fail['expected_outcome']!r}, actual={fail['actual_outcome']!r}")
    if not fail["bucket_ok"]:
        print(f"  BUCKET    : expected one of {fail['expected_buckets']}, actual {fail['actual_buckets']}")
    if not fail["repairs_required_ok"]:
        missing = [r for r in fail['expected_repairs'] if r not in fail['actual_repairs']]
        print(f"  MISSING   : repairs not applied: {missing}")
        print(f"              actual repairs: {fail['actual_repairs']}")
    if not fail["repairs_forbidden_ok"]:
        unwanted = [r for r in fail['expected_no_repairs'] if r in fail['actual_repairs']]
        print(f"  UNEXPECTED: forbidden repairs fired: {unwanted}")
    if not fail["prepared_ok"]:
        print(f"  PREPARED  :")
        print(f"    expected : {fail['expected_prepared']!r}")
        print(f"    actual   : {fail['actual_prepared']!r}")

# ----- Summary of failure categories -----
print()
print("=" * 88)
print("FAILURE CATEGORY SUMMARY")
print("=" * 88)
cat_counts = Counter()
for f in failures:
    if not f["outcome_ok"]:           cat_counts["outcome_mismatch"] += 1
    if not f["bucket_ok"]:            cat_counts["bucket_miss"] += 1
    if not f["repairs_required_ok"]:  cat_counts["missing_repair"] += 1
    if not f["repairs_forbidden_ok"]: cat_counts["wrong_repair_fired"] += 1
    if not f["prepared_ok"]:          cat_counts["prepared_text_mismatch"] += 1
for k, v in cat_counts.most_common():
    print(f"  {k:<30} {v:>5}")

# Write failures to disk
fp = os.path.join(os.path.dirname(__file__), "_synth_failures.jsonl")
with open(fp, "w", encoding="utf-8") as f:
    for fl in failures:
        f.write(json.dumps(fl, ensure_ascii=False) + "\n")
print(f"\nWrote {len(failures)} failure details to {fp}")
