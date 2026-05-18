"""Demonstrate autoheal on every failure bucket. Prints before -> after diff."""
import sys, os, io
# Force UTF-8 stdout so combining diacritics print on cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import prepare_text, label_buckets, BUCKET_DESCRIPTIONS


CASES = [
    ("A — missing delimiters",
     r"\alpha + \beta = -\frac{1}{6}",
     "rubric_criterion"),

    ("A — bare fraction",
     r"\frac{(\alpha + \beta)^2 - 2\alpha\beta}{\alpha\beta}",
     "rubric_criterion"),

    ("D — orphan eta (lost \\beta backslash)",
     r"$\alpha + eta + \alpha\beta$",
     "feedback"),

    ("D — orphan rac (lost \\frac backslash)",
     r"$\frac{1}{3} \times rac{2}{5}$",
     "feedback"),

    ("D — glued alphaeta",
     r"$\alpha + alphaeta = 5$",
     "feedback"),

    ("D — combining diacritic (Unicode U+0311)",
     "$\\alpha + \\beta + ̑\\alpha\\beta$",
     "feedback"),

    ("L — literal \\n in ai_solution",
     "Step 1: do thing.\\nStep 2: do other.",
     "ai_solution"),

    ("C — unbalanced/truncated dollar",
     "... $0.1 M$ and $0.5 M$. [Ka for $...",
     "authored_question"),

    ("H — fill-in-the-blank prompt",
     "The most electronegative element is ______",
     "authored_question"),

    ("J — currency-shaped text",
     "The book costs $5",
     "feedback"),

    ("F — HTML mixed in question body",
     "Find the statistics: <table><tr><td>1</td></tr></table>",
     "authored_question"),

    ("E — forbidden command (security)",
     r"$\input{/etc/passwd}$",
     "student_answer"),

    ("G — mixed prose + math (clean)",
     r"If $\alpha$ and $\beta$ are zeroes of $x^2 - 1$, find $\alpha + \beta$.",
     "authored_question"),

    ("K — nested text/math conflict",
     r"$\frac{1}{\text{\sqrt{3}}}$",
     "feedback"),

    ("Z — clean display math",
     r"$$\int_0^1 x^2 dx = \frac{1}{3}$$",
     "authored_question"),
]


def fmt(s, maxlen=80):
    s = repr(s)
    return s if len(s) <= maxlen else s[: maxlen - 3] + "...'"


def main():
    print("=" * 96)
    print("AUTO-HEAL DEMO — Real broken LaTeX inputs, healed by the pipeline")
    print("=" * 96)
    for label, text, fam in CASES:
        result = prepare_text(text, source_family=fam)
        buckets = label_buckets(text, result)
        bucket_strs = [b for b in buckets]
        print()
        print(f"### {label}")
        print(f"  family : {fam}")
        print(f"  buckets: {bucket_strs}")
        print(f"  in     : {fmt(text)}")
        print(f"  out    : {fmt(result.prepared_text)}")
        print(f"  repairs: {result.repairs_applied or '(none)'}")
        outcomes = [s.rendered_as for s in result.segments]
        print(f"  outcome: math={outcomes.count('math')}, text={outcomes.count('text')}, "
              f"fallback={outcomes.count('fallback')}")


if __name__ == "__main__":
    main()
