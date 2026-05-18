"""Extract every ParseError message string from the local katex.mjs source."""
import os, re, json, sys
from collections import Counter, defaultdict

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

PATH = os.path.join(os.path.dirname(__file__), "node_modules", "katex", "dist", "katex.mjs")
src = open(PATH, encoding="utf-8").read()
print(f"Loaded {PATH}  ({len(src):,} bytes)")

# KaTeX throws errors in several patterns:
#   throw new ParseError("...message...", token)
#   throw new ParseError(`tmpl ${...}`, token)
#   ParseError("...")
# Capture the FIRST string argument of every ParseError(...) call.

# A relaxed regex that handles both "..." and `...` literals (no nested quotes
# of the same kind, no escapes spanning the boundary).
PAT = re.compile(r"""ParseError\s*\(\s*(?:
        "((?:\\.|[^"\\])*)"
      | `((?:\\.|[^`\\])*)`
)""", re.VERBOSE)

raw_msgs = []
for m in PAT.finditer(src):
    raw_msgs.append(m.group(1) if m.group(1) is not None else m.group(2))

# Collapse identical messages; show count
counter = Counter(raw_msgs)
print(f"\nTotal ParseError(...) call-sites with string literal: {sum(counter.values())}")
print(f"Distinct error message templates:                       {len(counter)}")

# Normalize for categorization: replace `${...}` with <var>
def normalize(s):
    s = re.sub(r"\$\{[^}]*\}", "<var>", s)
    return s

categories = defaultdict(list)
for msg, n in counter.most_common():
    norm = normalize(msg)
    # Categorize by leading keyword(s)
    lower = norm.lower().strip()
    if lower.startswith("expected") or lower.startswith("expected '"):
        cat = "Expected-X — parser awaited specific token"
    elif "undefined control sequence" in lower:
        cat = "Undefined control sequence — unknown \\command"
    elif lower.startswith("invalid"):
        cat = "Invalid value (size / color / character / mode)"
    elif "must be" in lower or "must have" in lower or "must not" in lower:
        cat = "Constraint violation"
    elif "got" in lower and "expected" not in lower:
        cat = "Unexpected token / 'got X'"
    elif "argument" in lower:
        cat = "Function-argument errors"
    elif "missing" in lower:
        cat = "Missing-X"
    elif "delimit" in lower or "\\right" in lower or "\\left" in lower:
        cat = "Delimiter mismatch (\\left / \\right)"
    elif "environment" in lower:
        cat = "Environment errors (\\begin / \\end)"
    elif "color" in lower or "size" in lower or "unit" in lower:
        cat = "Color / size / unit parse error"
    elif "no such" in lower:
        cat = "No such X"
    elif "can't use" in lower or "cannot use" in lower or "not allowed" in lower:
        cat = "Mode mismatch (math/text/display)"
    elif "double" in lower or "duplicate" in lower:
        cat = "Double / duplicate / repeated"
    elif "unicode" in lower or "control word" in lower or "control symbol" in lower or "character" in lower:
        cat = "Lexical / character errors"
    elif "\\\\" in norm:
        cat = "Newline / tabular-row errors"
    else:
        cat = "Other"
    categories[cat].append((msg, n))

# Print categorized
print("\n" + "=" * 88)
print("FULL CATALOG OF KaTeX PARSE ERROR MESSAGE TEMPLATES")
print(f"(extracted from {os.path.relpath(PATH)})")
print("=" * 88)

# Stable category order: known categories first, then alphabetic
KNOWN = [
    "Expected-X — parser awaited specific token",
    "Undefined control sequence — unknown \\command",
    "Unexpected token / 'got X'",
    "Function-argument errors",
    "Constraint violation",
    "Missing-X",
    "Delimiter mismatch (\\left / \\right)",
    "Environment errors (\\begin / \\end)",
    "Mode mismatch (math/text/display)",
    "Color / size / unit parse error",
    "Invalid value (size / color / character / mode)",
    "Newline / tabular-row errors",
    "Lexical / character errors",
    "No such X",
    "Double / duplicate / repeated",
    "Other",
]
seen = set()
order = []
for c in KNOWN:
    if c in categories:
        order.append(c); seen.add(c)
for c in sorted(categories):
    if c not in seen:
        order.append(c)

for cat in order:
    items = sorted(categories[cat], key=lambda x: -x[1])
    print(f"\n## {cat}   ({len(items)} distinct, {sum(n for _,n in items)} call-sites)")
    for msg, n in items:
        c = f"  [x{n}]" if n > 1 else "       "
        print(f"  {c} {msg}")

# Write a structured catalog JSON next to the script
catalog = {
    "total_call_sites": sum(counter.values()),
    "distinct_templates": len(counter),
    "source_file": os.path.relpath(PATH),
    "categories": {
        cat: [{"message": m, "count": n} for m, n in sorted(items, key=lambda x: -x[1])]
        for cat, items in categories.items()
    },
}
out_path = os.path.join(os.path.dirname(__file__), "docs", "katex_error_catalog.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(catalog, f, indent=2, ensure_ascii=False)
print(f"\nWrote structured catalog to: {os.path.relpath(out_path)}")
