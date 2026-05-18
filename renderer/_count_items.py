"""Count the total LaTeX items available across every dataset file."""
import csv
import json
import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SYNTH_DIR = os.path.dirname(os.path.abspath(__file__))

def count_jsonl(path):
    if not os.path.exists(path): return None
    n = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n

def count_csv(path):
    if not os.path.exists(path): return None
    with open(path, "r", encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))

def size_mb(path):
    if not os.path.exists(path): return None
    return os.path.getsize(path) / (1024 * 1024)

FILES = [
    # (path, type, description, is_master)
    (os.path.join(ROOT, "classified_candidates.jsonl"),
     "jsonl", "MASTER dataset (everything classified)", True),
    (os.path.join(ROOT, "all_candidates.jsonl"),
     "jsonl", "Raw extracted candidate text", True),
    (os.path.join(ROOT, "confirmed_broken.csv"),
     "csv",   "Likely broken / raw-LaTeX rows", False),
    (os.path.join(ROOT, "confirmed_good.csv"),
     "csv",   "Rows that render cleanly", False),
    (os.path.join(ROOT, "tricky_examples.csv"),
     "csv",   "False positives + dangerous cases", False),
    (os.path.join(ROOT, "golden_test_set.csv"),
     "csv",   "Smaller curated review set", False),
    (os.path.join(ROOT, "labeled_sample.csv"),
     "csv",   "Balanced diverse sample", False),
    (os.path.join(SYNTH_DIR, "_synth_dataset.jsonl"),
     "jsonl", "Synthetic dataset (we generated)", False),
]

print("=" * 96)
print(f"  Total LaTeX items available for testing in:")
print(f"  D:\\latex_project\\latex_rendering_dataset_sanitized_20260514_192103\\…")
print("=" * 96)
print()
print(f"{'File':<35} {'Type':<6} {'Rows':>10} {'Size':>10}   Description")
print("-" * 96)

total_master_real = 0
total_subset_real = 0
total_synth = 0
counts = {}

for path, kind, desc, is_master in FILES:
    name = os.path.basename(path)
    if kind == "jsonl":
        n = count_jsonl(path)
    else:
        n = count_csv(path)
    sz = size_mb(path)
    counts[name] = n
    sz_str = f"{sz:>6.1f} MB" if sz is not None else "        —"
    n_str = f"{n:>10,}" if n is not None else "         —"
    print(f"{name:<35} {kind:<6} {n_str} {sz_str}   {desc}")
    if n is None:
        continue
    if name == "_synth_dataset.jsonl":
        total_synth += n
    elif is_master:
        total_master_real += n
    else:
        total_subset_real += n

print("-" * 96)
print()
print("=" * 96)
print(f"  HEADLINE COUNT")
print("=" * 96)
print(f"  classified_candidates.jsonl is the MASTER file:    {counts.get('classified_candidates.jsonl', 'N/A'):>10,}")
print(f"                                                      (every other CSV is a subset of this)")
print(f"  all_candidates.jsonl (pre-classification raw):     {counts.get('all_candidates.jsonl', 'N/A'):>10,}")
print()

cb = counts.get("confirmed_broken.csv", 0) or 0
cg = counts.get("confirmed_good.csv", 0) or 0
tr = counts.get("tricky_examples.csv", 0) or 0
gt = counts.get("golden_test_set.csv", 0) or 0
ls = counts.get("labeled_sample.csv", 0) or 0
sn = counts.get("_synth_dataset.jsonl", 0) or 0

print(f"  Curated CSV slices (subsets of master, may overlap):")
print(f"    confirmed_broken.csv:                            {cb:>10,}")
print(f"    confirmed_good.csv:                              {cg:>10,}")
print(f"    tricky_examples.csv:                             {tr:>10,}")
print(f"    golden_test_set.csv:                             {gt:>10,}")
print(f"    labeled_sample.csv:                              {ls:>10,}")
print(f"    -- sum of slices (with overlaps):                {cb+cg+tr+gt+ls:>10,}")
print()
print(f"  Synthetic dataset (we generated, fully independent):")
print(f"    _synth_dataset.jsonl:                            {sn:>10,}")
print()
print("=" * 96)
print(f"  UNIQUE TESTABLE ROWS")
print("=" * 96)
master = counts.get("classified_candidates.jsonl", 0) or 0
print(f"  Real production rows (deduplicated via master):    {master:>10,}")
print(f"  Synthetic rows (generated):                        {sn:>10,}")
print(f"  -- GRAND TOTAL unique testable items:              {master + sn:>10,}")
