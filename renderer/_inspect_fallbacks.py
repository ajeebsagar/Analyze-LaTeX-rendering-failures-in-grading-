"""For every fallback row in out_solid/all_candidates/results.jsonl, recover
the original metadata from all_candidates.jsonl (joined by row order) and
print a categorized breakdown of WHICH cases the autofixer punted on.

Output: a categorized list grouping rows by their validation reason, plus
exact raw_text excerpts so we can see the actual issues.
"""
import json
import os
import sys
from collections import defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_FILE = os.path.join(ROOT, "all_candidates.jsonl")
RESULTS_FILE = os.path.join(os.path.dirname(__file__),
                            "out_solid", "all_candidates", "results.jsonl")


def iter_pairs():
    """Walk source + results in parallel (they are in the same order)."""
    with open(SRC_FILE, encoding="utf-8") as src_f, \
         open(RESULTS_FILE, encoding="utf-8") as res_f:
        for src_line, res_line in zip(src_f, res_f):
            try:
                src = json.loads(src_line)
                res = json.loads(res_line)
            except json.JSONDecodeError:
                continue
            yield src, res


# Walk all rows; keep only fallbacks
groups = defaultdict(list)        # reason -> [rows]
by_source_table = defaultdict(int)
by_ui_surface = defaultdict(int)
by_field_path = defaultdict(int)
by_subject = defaultdict(int)
by_tenant = defaultdict(int)
by_buckets = defaultdict(int)

n_total = 0
for src, res in iter_pairs():
    n_total += 1
    if not res.get("had_fallback"):
        continue
    # Pull per-segment validation reasons; group by the primary reason
    primary_reason = "unknown"
    for seg in res.get("segments", []):
        if seg.get("outcome") == "fallback":
            reasons = seg.get("validation_reasons") or []
            if reasons:
                primary_reason = reasons[0]
                break

    by_source_table[src.get("source_table", "?")] += 1
    by_ui_surface[src.get("ui_surface", "?")] += 1
    by_field_path[src.get("field_path", "?")] += 1
    by_subject[src.get("subject_name", "?")] += 1
    by_tenant[src.get("tenant", "?")] += 1
    for b in res.get("buckets", []):
        by_buckets[b] += 1

    groups[primary_reason].append({
        "row_number": n_total,             # 1-based position in the input
        "raw_text": src.get("raw_text") or "",
        "field_path": src.get("field_path"),
        "ui_surface": src.get("ui_surface"),
        "source_table": src.get("source_table"),
        "subject": src.get("subject_name"),
        "grade": src.get("grade_name"),
        "tenant": src.get("tenant"),
        "buckets": res.get("buckets", []),
        "all_validation_reasons": [
            r for s in res.get("segments", []) for r in (s.get("validation_reasons") or [])
        ],
        "n_segments": len(res.get("segments", [])),
    })

n_fb = sum(len(v) for v in groups.values())

print("=" * 96)
print(f"FALLBACK ROW INSPECTION — autofix pipeline on all_candidates.jsonl")
print("=" * 96)
print(f"  Source file       : {SRC_FILE}")
print(f"  Results file      : {RESULTS_FILE}")
print(f"  Total rows scanned: {n_total:,}")
print(f"  Rows with fallback: {n_fb}  ({n_fb*100/n_total:.3f}%)")

print()
print("=" * 96)
print("BREAKDOWN BY PRIMARY VALIDATION REASON")
print("=" * 96)
for reason in sorted(groups, key=lambda k: -len(groups[k])):
    print(f"  {reason:<32} {len(groups[reason]):>4} rows")

print()
print("=" * 96)
print("BREAKDOWN BY ORIGIN (where the fallbacks came from)")
print("=" * 96)
print(f"  By source_table:")
for k, v in sorted(by_source_table.items(), key=lambda x: -x[1]):
    print(f"    {k:<35}  {v:>4}")
print(f"\n  By ui_surface:")
for k, v in sorted(by_ui_surface.items(), key=lambda x: -x[1]):
    print(f"    {k:<35}  {v:>4}")
print(f"\n  By subject:")
for k, v in sorted(by_subject.items(), key=lambda x: -x[1]):
    print(f"    {k:<35}  {v:>4}")
print(f"\n  By tenant:")
for k, v in sorted(by_tenant.items(), key=lambda x: -x[1]):
    print(f"    {k:<35}  {v:>4}")
print(f"\n  Buckets fired:")
for k, v in sorted(by_buckets.items(), key=lambda x: -x[1]):
    print(f"    bucket {k:<3} {v:>4}")

print()
print("=" * 96)
print("FALLBACK EXAMPLES — every reason, with raw text + source field_path")
print("=" * 96)

for reason in sorted(groups, key=lambda k: -len(groups[k])):
    rows = groups[reason]
    print(f"\n──────────────────────────────────────────────────────────────────────────")
    print(f"  REASON: {reason}   ({len(rows)} row(s))")
    print(f"──────────────────────────────────────────────────────────────────────────")
    # Show ALL if reason has <= 10; otherwise show first 5 + last 5
    show = rows if len(rows) <= 10 else rows[:5] + rows[-5:]
    for r in show:
        raw = r["raw_text"] or ""
        raw_short = raw if len(raw) <= 200 else raw[:197] + "..."
        print()
        print(f"  [row {r['row_number']:>7,}]   {r['source_table']}   {r['ui_surface']}")
        print(f"    field_path : {r['field_path']}")
        print(f"    subject    : {r['subject']} · grade={r['grade']} · tenant={r['tenant']}")
        print(f"    buckets    : {r['buckets']}")
        print(f"    n_segments : {r['n_segments']}")
        print(f"    raw        : {raw_short!r}")

# Write a JSONL with every fallback row for offline analysis
out_path = os.path.join(os.path.dirname(__file__), "out_solid", "all_candidates", "fallback_rows.jsonl")
with open(out_path, "w", encoding="utf-8") as f:
    for reason, rows in groups.items():
        for r in rows:
            f.write(json.dumps({"reason": reason, **r}, ensure_ascii=False) + "\n")
print(f"\n\nAlso wrote a JSONL of all fallback rows to:\n  {out_path}")
