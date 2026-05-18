"""Side-by-side: KaTeX failure mode vs Python diagnostic vs final autoheal."""
import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path: sys.path.insert(0, _src)

from latex_pipeline import build_default_pipeline, ErrorAnalyzer

pipeline = build_default_pipeline()
analyzer = ErrorAnalyzer()

# For each input we report:
#   1. What KaTeX would emit (predicted from KaTeX's behavior)
#   2. What our Python diagnostic identifies BEFORE KaTeX
#   3. What the autoheal produces (KaTeX-ready, healed)
CASES = [
    ("Missing closing brace",     r"\frac{1}{2",                   "rubric_criterion"),
    ("Missing $ wrappers",        r"\alpha + \beta = -\frac{1}{6}", "rubric_criterion"),
    ("Orphan \\beta -> eta",      r"$\alpha + eta + \alpha\beta$",  "feedback"),
    ("Orphan \\frac -> rac",      r"$\frac{1}{3} \times rac{2}{5}$", "feedback"),
    ("Compound: missing $ + eta", r"\alpha + eta = -\frac{1}{6}$",  "rubric_criterion"),
    ("Combining diacritic",       "$\\alpha + \\beta + ̑\\alpha$",  "feedback"),
    ("Fill-in-the-blank",         "Element is ______",              "authored_question"),
    ("Forbidden command",         r"$\input{/etc/passwd}$",         "student_answer"),
]

def short(s, n=70):
    return s if len(s) <= n else s[:n-3] + "..."

print()
print("█" * 90)
print("  KaTeX raw failure  vs  Python diagnostic  vs  Autoheal output")
print("█" * 90)

for label, raw, fam in CASES:
    print()
    print("─" * 90)
    print(f"  {label}")
    print("─" * 90)
    print(f"  INPUT          : {raw!r}")

    # 1. Predicted KaTeX raw behavior (annotated based on KaTeX 0.16.x semantics)
    print("\n  ► If you fed this DIRECTLY to KaTeX (no pipeline):")
    if "\\frac{1}{2" == raw:
        print("      throwOnError=true  : ParseError 'Unexpected end of input in a")
        print("                            macro argument, expected }' at position 10")
        print("      throwOnError=false : red <span class=\"katex-error\"")
        print("                            title=\"...\" >\\frac{1}{2</span>")
    elif raw.startswith("\\alpha + \\beta = -"):
        print("      KaTeX renderToString accepts this fine (no $ needed when called")
        print("      directly). But in BROWSER auto-render mode, no $..$ means KaTeX")
        print("      never enters math mode → text shows literal \\alpha\\beta\\frac.")
    elif "eta" in raw and "alpha + eta" in raw:
        print("      KaTeX renders successfully but produces WRONG output: 'eta' is")
        print("      typeset as the three letters e, t, a — NOT as Greek β.")
        print("      THIS IS THE DANGEROUS CASE: no error message, just wrong math.")
    elif "rac{" in raw:
        print("      Like the eta case: KaTeX renders 'rac' as three literal letters")
        print("      r, a, c — silently producing wrong math. No error fired.")
    elif "\\input" in raw:
        print("      throwOnError=true  : ParseError 'Undefined control sequence: \\input'")
        print("                            at position 0")
        print("      throwOnError=false : red error span")
    elif "______" in raw:
        print("      throwOnError=true  : ParseError 'Expected group after _' at position 12")
        print("      throwOnError=false : red error span")
    elif "̑" in raw:
        print("      KaTeX renders but combining diacritic produces visually corrupted")
        print("      glyph stacking — no error, just wrong output.")

    # 2. Python diagnostic
    print("\n  ► Python ErrorAnalyzer diagnostic (pre-parse):")
    rep = analyzer.analyze(raw)
    if not rep.has_errors:
        print("      (no issues detected)")
    for i, iss in enumerate(rep.issues, 1):
        msg = f"      [{i}] {iss.kind} @ pos {iss.position}"
        if iss.found:   msg += f"  found={iss.found!r}"
        if iss.missing: msg += f"  missing={iss.missing!r}"
        print(msg)

    # 3. Autoheal output
    print("\n  ► Autoheal (full pipeline) output:")
    res = pipeline.run(raw, source_family=fam)
    n_math = sum(1 for s in res.segments if s.outcome.value == "math")
    n_fb = sum(1 for s in res.segments if s.outcome.value == "fallback")
    print(f"      buckets : {','.join(res.buckets)}")
    print(f"      repairs : {','.join(res.repairs_applied) or '(none)'}")
    print(f"      output  : {short(res.prepared_text)!r}")
    print(f"      render  : {n_math} math span(s), {n_fb} fallback span(s)")

print()
print("█" * 90)
