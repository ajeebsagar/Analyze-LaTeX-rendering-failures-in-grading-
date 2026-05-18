"""End-to-end autoheal verification.

For every named case (correct + broken), assert the pipeline's healed
output matches a known-correct expected string OR a known-correct property
(no fallback, etc).
"""
import os, sys, io
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

_src = os.path.join(os.path.dirname(os.path.abspath(__file__)), "src")
if _src not in sys.path: sys.path.insert(0, _src)

from latex_pipeline import build_default_pipeline, RenderOutcome

pipeline = build_default_pipeline()

# (label, input, family, expected_prepared_OR_None, must_have_repair, must_not_fallback, expected_buckets)
CASES = [
    # === CORRECT LaTeX (no repairs should happen) ===
    ("CORRECT: clean inline math",
     r"If $\alpha$ and $\beta$ are zeroes of $x^2 - 1$.",
     "authored_question",
     r"If $\alpha$ and $\beta$ are zeroes of $x^2 - 1$.",
     None, True, ["G"]),
    ("CORRECT: display math",
     r"$$\int_0^1 x^2 dx = \frac{1}{3}$$",
     "authored_question",
     r"$$\int_0^1 x^2 dx = \frac{1}{3}$$",
     None, True, ["Z"]),
    ("CORRECT: cases env",
     r"$f(x) = \begin{cases} x^2 & 0\leq x \leq 3 \\ 9x & 3 < x \leq 10 \end{cases}$",
     "authored_question",
     r"$f(x) = \begin{cases} x^2 & 0\leq x \leq 3 \\ 9x & 3 < x \leq 10 \end{cases}$",
     None, True, ["Z"]),
    ("CORRECT: \\(...\\) delim",
     r"We have \(\alpha + \beta\) here.",
     "authored_question",
     r"We have \(\alpha + \beta\) here.",
     None, True, ["G"]),
    ("CORRECT: currency prose (not math)",
     "The book costs $5 only.",
     "feedback",
     "The book costs $5 only.",
     None, True, ["C"]),  # odd-dollar -> bucket C, but no fallback

    # === BROKEN LaTeX (must auto-heal) ===
    ("BROKEN: missing delim",
     r"\alpha + \beta = -\frac{1}{6}",
     "rubric_criterion",
     r"$\alpha + \beta = -\frac{1}{6}$",
     "wrap_math_only", True, ["A"]),
    ("BROKEN: orphan eta -> \\beta",
     r"$\alpha + eta + \alpha\beta$",
     "feedback",
     r"$\alpha + \beta + \alpha\beta$",
     "repair_orphan_eta_to_beta", True, ["D"]),
    ("BROKEN: orphan rac -> \\frac",
     r"$\frac{1}{3} \times rac{2}{5}$",
     "feedback",
     r"$\frac{1}{3} \times \frac{2}{5}$",
     "repair_orphan_rac", True, ["D"]),
    ("BROKEN: glued alphaeta",
     r"$\alpha + alphaeta = 5$",
     "feedback",
     r"$\alpha + \alpha\beta = 5$",
     "repair_alphaeta", True, ["D"]),
    ("BROKEN: combining diacritic",
     "$\\alpha + \\beta + ̑\\alpha\\beta$",
     "feedback",
     r"$\alpha + \beta + \alpha\beta$",
     "strip_combining_diacritics", True, ["D"]),
    ("BROKEN: literal \\n in ai_solution",
     "Step 1: do thing.\\nStep 2: do other.",
     "ai_solution",
     "Step 1: do thing.\nStep 2: do other.",
     "literal_escape_to_whitespace", True, ["L"]),
    ("BROKEN: truncated $",
     "... $0.1M$ and $0.5M$. [Ka for $...",
     "authored_question",
     None, None, True, ["C"]),
    ("BROKEN: HTML table -> HTML-aware passthrough",
     "<table><tr><td>1</td></tr></table>",
     "authored_question",
     None, None, True, ["F"]),   # tags pass through verbatim; no fallback now
    ("BROKEN: forbidden command -> fallback",
     r"$\input{/etc/passwd}$",
     "student_answer",
     None, None, False, ["E"]),
    ("BROKEN: fill-in-the-blank -> not math",
     "The most electronegative element is ______",
     "authored_question",
     "The most electronegative element is ______",
     None, True, ["Z"]),  # rendered as plain text, no fallback
]

print(f"{'STATUS':<6} {'LABEL':<50}  {'BUCKETS':<10}  REPAIRS")
print("-" * 110)

passes = 0
fails = 0
for label, text, fam, expected, must_repair, must_not_fb, expected_buckets in CASES:
    r = pipeline.run(text, source_family=fam)
    had_fb = any(s.outcome is RenderOutcome.FALLBACK for s in r.segments)
    ok = True
    reason = ""

    if expected is not None and r.prepared_text != expected:
        ok = False
        reason = f"prepared_text mismatch:\n    got: {r.prepared_text!r}\n    exp: {expected!r}"
    elif must_repair and must_repair not in r.repairs_applied:
        ok = False
        reason = f"missing repair {must_repair!r}; got {r.repairs_applied}"
    elif must_not_fb and had_fb:
        ok = False
        reason = f"unexpected fallback; reasons={r.failure_reasons}"
    elif (not must_not_fb) and not had_fb:
        ok = False
        reason = f"expected fallback but did not get one"
    else:
        # Check bucket presence (at least one expected bucket fired)
        if expected_buckets and not any(b in r.buckets for b in expected_buckets):
            ok = False
            reason = f"none of expected buckets {expected_buckets} fired; got {r.buckets}"

    status = "PASS" if ok else "FAIL"
    print(f"{status:<6} {label:<50}  {','.join(r.buckets):<10}  {','.join(r.repairs_applied)}")
    if not ok:
        print(f"       -> {reason}")
        fails += 1
    else:
        passes += 1

print()
print(f"Total: {passes}/{len(CASES)} passed, {fails} failed.")
sys.exit(0 if fails == 0 else 1)
