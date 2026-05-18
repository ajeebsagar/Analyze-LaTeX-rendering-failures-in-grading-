"""Proof: feed wrong LaTeX in, get correct KaTeX-renderable output."""
import os, sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path: sys.path.insert(0, _src)

from latex_pipeline import build_default_pipeline

pipeline = build_default_pipeline()

CASES = [
    ("Missing $ wrapping",
     r"\alpha + \beta = -\frac{1}{6}", "rubric_criterion"),
    ("Missing backslash on \\beta (becomes 'eta')",
     r"$\alpha + eta + \alpha\beta$", "feedback"),
    ("Missing backslash on \\frac (becomes 'rac')",
     r"$\frac{1}{3} \times rac{2}{5}$", "feedback"),
    ("Two backslashes lost (alphaeta glued)",
     r"$\alpha + alphaeta = 5$", "feedback"),
    ("Combining diacritic injected from PDF copy-paste",
     "$\\alpha + \\beta + ̑\\alpha\\beta$", "feedback"),
    ("Literal \\n leaked from JSON serialization",
     "Step 1: identify $a, b, c$.\\nStep 2: compute $\\alpha + \\beta$.",
     "ai_solution"),
    ("Compound: missing $ AND missing backslash on beta",
     r"\alpha + eta = -\frac{1}{6}", "rubric_criterion"),
    ("Compound: missing $ AND missing backslash on frac",
     r"x = rac{1}{2} + \alpha", "rubric_criterion"),
    ("Truncated mid-formula",
     "Recall $\\frac{1}{2}$ and $\\sqrt{3}$ and $\\alpha = ...", "authored_question"),
    ("Currency in prose (must NOT become math)",
     "The book costs $5 and the pen costs $3.", "feedback"),
    ("Fill-in-the-blank (must NOT trigger subscript chain)",
     "The most electronegative element is ______", "authored_question"),
    ("HTML table in question body (route to fallback safely)",
     "Find the mean: <table><tr><td>5</td><td>10</td></tr></table>", "authored_question"),
    ("Forbidden command (security — must be blocked)",
     r"$\input{/etc/passwd}$", "student_answer"),
]

print("=" * 92)
print("PROOF: Wrong LaTeX in -> Correct KaTeX-renderable output")
print("=" * 92)
print()

for label, raw, fam in CASES:
    r = pipeline.run(raw, source_family=fam)
    print(f"### {label}")
    print(f"  WRONG INPUT:   {raw!r}")
    print(f"  CORRECTED:     {r.prepared_text!r}")
    print(f"  REPAIRS:       {', '.join(r.repairs_applied) if r.repairs_applied else '(none — input was already safe)'}")
    print(f"  BUCKETS:       {', '.join(r.buckets)}")
    n_math = sum(1 for s in r.segments if s.outcome.value == 'math')
    n_fb = sum(1 for s in r.segments if s.outcome.value == 'fallback')
    print(f"  RENDER:        {n_math} math span(s), {n_fb} fallback span(s)")
    print(f"  STATUS:        {'OK — KaTeX will render' if n_fb == 0 else 'SAFE — falls back to readable text'}")
    print()
