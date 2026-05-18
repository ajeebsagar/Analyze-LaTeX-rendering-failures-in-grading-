"""Run the pipeline on 5,000 real rows, then run it again on the prepared
output. The prepared text must be byte-equal — i.e. repair is idempotent.
Also asserts zero pipeline exceptions.
"""
import json, os, sys, time
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path: sys.path.insert(0, _src)

from latex_pipeline import build_default_pipeline

pipeline = build_default_pipeline()

INPUT = os.path.join(os.path.dirname(__file__), "out_solid", "full", "results.jsonl")
LIMIT = 5000

n_checked = n_diff = n_throw = 0
diffs = []

t0 = time.time()
with open(INPUT, "r", encoding="utf-8") as f:
    for line in f:
        if n_checked >= LIMIT: break
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        prepared = rec.get("prepared_text")
        if prepared is None: continue
        fam = rec.get("family", "unknown")
        try:
            r2 = pipeline.run(prepared, source_family=fam)
        except Exception as exc:
            n_throw += 1
            continue
        if r2.prepared_text != prepared:
            n_diff += 1
            if len(diffs) < 3:
                diffs.append((rec.get("dataset_row_id"), prepared[:120], r2.prepared_text[:120]))
        n_checked += 1
elapsed = time.time() - t0

print(f"Checked: {n_checked} rows in {elapsed:.2f}s")
print(f"Non-idempotent rows: {n_diff} ({n_diff*100/max(n_checked,1):.3f}%)")
print(f"Pipeline exceptions: {n_throw}")
for did, a, b in diffs:
    print(f"  {did}:")
    print(f"    1st: {a!r}")
    print(f"    2nd: {b!r}")
sys.exit(0 if (n_diff == 0 and n_throw == 0) else 1)
