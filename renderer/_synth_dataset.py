"""Generate a 1,000-row synthetic LaTeX rendering dataset with KNOWN-CORRECT
expected labels for every row.

Design goals:
- Use math vocabulary NOT prominent in the original corpus (tensor calculus,
  statistical mechanics, topology, advanced linear algebra) to avoid
  pattern overlap with `confirmed_broken.csv`.
- Cover every bucket A..L plus clean Z.
- For every row, the expected outcome, bucket, and repair set are known
  deterministically so the pipeline's accuracy can be measured.

Output: `_synth_dataset.jsonl` — one row per line with fields:
  id              str
  raw             str   (the broken or clean input)
  source_family   str   (which family prior to use)
  expected_outcome str  ('math' | 'text' | 'fallback')
  expected_buckets list[str]  (one or more bucket labels we expect to fire)
  expected_repairs list[str]  (repair names that MUST appear in result.repairs_applied)
  expected_no_repairs list[str]  (repair names that MUST NOT fire — anti-tests)
  expected_prepared str | null   (if deterministic, the exact KaTeX-ready output)
"""
from __future__ import annotations

import json
import os
import random
import sys

# Fresh math content NOT prominent in the corpus
INTEGRALS = [
    r"\int_{-\infty}^{\infty} e^{-x^2} dx",
    r"\oint_{\partial \Omega} \vec{F} \cdot d\vec{r}",
    r"\iint_D \nabla \times \vec{B} \, dA",
    r"\int_0^{2\pi} \cos^2(\theta) \, d\theta",
    r"\int e^{-\lambda x} dx",
]
SUMS = [
    r"\sum_{n=1}^{\infty} \frac{1}{n^2}",
    r"\sum_{k=0}^{N} \binom{N}{k} p^k (1-p)^{N-k}",
    r"\prod_{i=1}^{n} (1 + x_i)",
    r"\sum_{p \text{ prime}} \frac{1}{p}",
]
PHYSICS = [
    r"\hat{H} \psi = E \psi",
    r"\nabla \cdot \vec{E} = \frac{\rho}{\epsilon_0}",
    r"R_{\mu\nu} - \frac{1}{2} g_{\mu\nu} R = 8\pi T_{\mu\nu}",
    r"|\psi\rangle = \alpha |0\rangle + \beta |1\rangle",
    r"S = -k_B \sum_i p_i \ln p_i",
]
LINALG = [
    r"\det(A - \lambda I) = 0",
    r"A = U \Sigma V^\top",
    r"\langle u, v \rangle = \sum_i u_i \bar{v_i}",
    r"\|x\|_2 = \sqrt{\sum_i x_i^2}",
]
NT_AND_TOPO = [
    r"\zeta(s) = \prod_p \frac{1}{1 - p^{-s}}",
    r"\pi_1(S^1) = \mathbb{Z}",
    r"H_n(X; \mathbb{Z}) \cong H^n(X; \mathbb{Z})",
    r"\gcd(a, b) = \gcd(b, a \bmod b)",
]
ALL_MATH = INTEGRALS + SUMS + PHYSICS + LINALG + NT_AND_TOPO

PROSE_BEFORE = [
    "Consider", "Recall that", "Note", "Therefore", "Hence we obtain",
    "By definition,", "It follows that", "We claim", "Suppose",
    "For all measurable functions,", "In the limit",
]
PROSE_AFTER = [
    "for every test function.", "in the weak topology.",
    "as a corollary.", "by standard results.",
    "modulo a constant factor.", "almost everywhere.",
    "in the distributional sense.", "in the case of complete metric spaces.",
]

# Deterministic seed for reproducibility
rng = random.Random(20260518)


def make_id(i: int) -> str:
    return f"synth-{i:04d}"


def gen_bucket_A(i: int) -> dict:
    """Math-only content, no delimiters. Source family = rubric_criterion to
    trigger wrap_math_only."""
    m = rng.choice(ALL_MATH)
    return {
        "id": make_id(i), "raw": m, "source_family": "rubric_criterion",
        "expected_outcome": "math",
        "expected_buckets": ["A"],
        "expected_repairs": ["wrap_math_only"],
        "expected_no_repairs": [],
        "expected_prepared": f"${m}$",
    }


def gen_bucket_B(i: int) -> dict:
    """Broken braces — unbalanced. Pipeline should fallback (or salvage some
    segments) — at minimum, must not crash."""
    base = rng.choice(ALL_MATH)
    # Drop the last closing brace by index
    if "}" in base:
        # Remove the LAST } so braces are unbalanced
        idx = base.rfind("}")
        broken = base[:idx] + base[idx+1:]
    else:
        broken = base + "{"
    # Wrap with $..$ so the segmenter creates a math segment
    raw = "$" + broken + "$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "feedback",
        "expected_outcome": "fallback",
        "expected_buckets": ["B"],
        "expected_repairs": [],
        "expected_no_repairs": ["wrap_math_only"],
        "expected_prepared": None,  # don't require exact, just fallback
    }


def gen_bucket_C(i: int) -> dict:
    """Unbalanced dollar — single orphan $ at start or end of math-only string."""
    m = rng.choice(ALL_MATH)
    side = rng.choice(["leading", "trailing"])
    raw = ("$" + m) if side == "leading" else (m + "$")
    return {
        "id": make_id(i), "raw": raw, "source_family": "rubric_criterion",
        "expected_outcome": "math",
        "expected_buckets": ["A", "C"],   # autohealer strips the orphan + wraps
        "expected_repairs": ["wrap_math_only_strip_orphan_dollar"],
        "expected_no_repairs": [],
        "expected_prepared": f"${m}$",
    }


def gen_bucket_D_eta(i: int) -> dict:
    """OCR corruption — orphan eta (should be \\beta)."""
    raw = r"$\alpha + eta + \alpha\beta + \frac{1}{2}$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "feedback",
        "expected_outcome": "math",
        "expected_buckets": ["D"],
        "expected_repairs": ["repair_orphan_eta_to_beta"],
        "expected_no_repairs": [],
        "expected_prepared": r"$\alpha + \beta + \alpha\beta + \frac{1}{2}$",
    }


def gen_bucket_D_rac(i: int) -> dict:
    """OCR corruption — orphan rac."""
    raw = r"$\sum_n \frac{1}{n} + rac{a}{b}$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "feedback",
        "expected_outcome": "math",
        "expected_buckets": ["D"],
        "expected_repairs": ["repair_orphan_rac"],
        "expected_no_repairs": [],
        "expected_prepared": r"$\sum_n \frac{1}{n} + \frac{a}{b}$",
    }


def gen_bucket_D_diacritic(i: int) -> dict:
    """OCR corruption — combining diacritic injected."""
    raw = "$\\hat{H} \\psi + ̑\\alpha = E\\psi$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "feedback",
        "expected_outcome": "math",
        "expected_buckets": ["D"],
        "expected_repairs": ["strip_combining_diacritics"],
        "expected_no_repairs": [],
        "expected_prepared": r"$\hat{H} \psi + \alpha = E\psi$",
    }


def gen_bucket_D_alphaeta(i: int) -> dict:
    """OCR corruption — glued alphaeta."""
    raw = r"$\hat{p} = alphaeta \cdot k$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "feedback",
        "expected_outcome": "math",
        "expected_buckets": ["D"],
        "expected_repairs": ["repair_alphaeta"],
        "expected_no_repairs": [],
        "expected_prepared": r"$\hat{p} = \alpha\beta \cdot k$",
    }


def gen_bucket_E(i: int) -> dict:
    """Forbidden command — must fallback for security."""
    cmd = rng.choice(["input", "include", "write", "openout", "href", "url", "includegraphics"])
    raw = f"$\\{cmd}{{some_arg}}$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "student_answer",
        "expected_outcome": "fallback",
        "expected_buckets": ["E"],
        "expected_repairs": [],
        "expected_no_repairs": [],
        "expected_prepared": None,
    }


def gen_bucket_F(i: int) -> dict:
    """Unsupported environment — HTML mixed with text. Pipeline now
    processes HTML-aware: tags pass through verbatim, math inside still
    renders. Expected outcome is `text` (no math segments in these samples)
    because they contain only HTML + plain prose."""
    body = rng.choice([
        "<table><tr><td>1</td><td>2</td></tr></table>",
        "<p>Hello <strong>world</strong></p>",
        "Look: <table><thead><tr><th>x</th></tr></thead><tbody><tr><td>1</td></tr></tbody></table>",
    ])
    return {
        "id": make_id(i), "raw": body, "source_family": "authored_question",
        "expected_outcome": "text",
        "expected_buckets": ["F"],
        "expected_repairs": [],
        "expected_no_repairs": ["wrap_math_only"],
        "expected_prepared": None,
    }


def gen_bucket_G(i: int) -> dict:
    """Clean mixed prose + math."""
    pre = rng.choice(PROSE_BEFORE)
    m1 = rng.choice(ALL_MATH)
    m2 = rng.choice(ALL_MATH)
    post = rng.choice(PROSE_AFTER)
    raw = f"{pre} ${m1}$ and ${m2}$, {post}"
    return {
        "id": make_id(i), "raw": raw, "source_family": "authored_question",
        "expected_outcome": "math",
        "expected_buckets": ["G"],
        "expected_repairs": [],
        "expected_no_repairs": ["wrap_math_only"],
        "expected_prepared": raw,
    }


def gen_bucket_H_fillblank(i: int) -> dict:
    """Fill-in-the-blank — must NOT enter math mode."""
    raw = rng.choice([
        "The eigenvalue is ______",
        "Hilbert space is denoted by ________",
        "_____ measure on the Borel sigma-algebra",
    ])
    return {
        "id": make_id(i), "raw": raw, "source_family": "authored_question",
        "expected_outcome": "text",
        "expected_buckets": ["Z"],
        "expected_repairs": [],
        "expected_no_repairs": ["wrap_math_only"],
        "expected_prepared": raw,
    }


def gen_bucket_I(i: int) -> dict:
    """Code snippet — must not be parsed as math."""
    raw = rng.choice([
        "```python\nprint('hello')\n```",
        "Use the command `npm install`.",
        "<pre>x := 5;</pre>",
    ])
    return {
        "id": make_id(i), "raw": raw, "source_family": "feedback",
        "expected_outcome": "text",   # most code paths render as text
        "expected_buckets": ["I"],
        "expected_repairs": [],
        "expected_no_repairs": ["wrap_math_only"],
        "expected_prepared": None,
    }


def gen_bucket_J(i: int) -> dict:
    """Currency text — must NOT auto-wrap, must NOT enter math mode."""
    raw = rng.choice([
        "The textbook costs $39.95 only.",
        "Membership fee: $12 per month.",
        "Subscription is $9 plus tax.",
    ])
    return {
        "id": make_id(i), "raw": raw, "source_family": "feedback",
        "expected_outcome": "text",
        "expected_buckets": ["C", "J"],   # odd $ triggers C, currency triggers J
        "expected_repairs": [],
        "expected_no_repairs": ["wrap_math_only", "wrap_math_only_strip_orphan_dollar"],
        "expected_prepared": None,
    }


def gen_bucket_K(i: int) -> dict:
    """Nested text/math conflict."""
    raw = r"$\frac{1}{\text{\sqrt{3}}}$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "feedback",
        "expected_outcome": "math",   # passthrough with strict:'ignore'
        "expected_buckets": ["K"],
        "expected_repairs": [],
        "expected_no_repairs": [],
        "expected_prepared": raw,
    }


def gen_bucket_L(i: int) -> dict:
    """Multiline AI-solution with literal \\n."""
    a = rng.choice(["Step 1", "First", "Setup"])
    b = rng.choice(["Step 2", "Next", "Solve"])
    raw = f"{a}: consider the integral.\\n{b}: evaluate at the limits."
    expected = raw.replace("\\n", "\n")
    return {
        "id": make_id(i), "raw": raw, "source_family": "ai_solution",
        "expected_outcome": "text",
        "expected_buckets": ["L"],
        "expected_repairs": ["literal_escape_to_whitespace"],
        "expected_no_repairs": [],
        "expected_prepared": expected,
    }


def gen_bucket_Z_inline(i: int) -> dict:
    """Clean inline math — must not be touched."""
    m = rng.choice(ALL_MATH)
    raw = f"${m}$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "authored_question",
        "expected_outcome": "math",
        "expected_buckets": ["Z"],
        "expected_repairs": [],
        "expected_no_repairs": ["wrap_math_only", "repair_orphan_eta_to_beta",
                                 "repair_orphan_rac", "strip_combining_diacritics"],
        "expected_prepared": raw,
    }


def gen_bucket_Z_display(i: int) -> dict:
    """Clean display math."""
    m = rng.choice(ALL_MATH)
    raw = f"$${m}$$"
    return {
        "id": make_id(i), "raw": raw, "source_family": "authored_question",
        "expected_outcome": "math",
        "expected_buckets": ["Z"],
        "expected_repairs": [],
        "expected_no_repairs": ["wrap_math_only"],
        "expected_prepared": raw,
    }


# ------- Distribution: ~1000 rows, weighted to mirror corpus -------
GENERATORS = [
    (gen_bucket_A, 200),         # 20%
    (gen_bucket_G, 200),         # 20%
    (gen_bucket_Z_inline, 120),  # 12%
    (gen_bucket_Z_display, 80),  # 8%
    (gen_bucket_D_eta, 60),      # 6%
    (gen_bucket_D_rac, 60),      # 6%
    (gen_bucket_D_diacritic, 40),# 4%
    (gen_bucket_D_alphaeta, 40), # 4%
    (gen_bucket_C, 80),          # 8%
    (gen_bucket_L, 60),          # 6%
    (gen_bucket_J, 30),          # 3%
    (gen_bucket_F, 10),          # 1%
    (gen_bucket_H_fillblank, 10),# 1%
    (gen_bucket_B, 5),           # 0.5%
    (gen_bucket_E, 5),           # 0.5%
    (gen_bucket_I, 5),           # 0.5%
    (gen_bucket_K, 5),           # 0.5%
]


def main():
    out = []
    idx = 0
    for gen, n in GENERATORS:
        for _ in range(n):
            out.append(gen(idx))
            idx += 1
    # Final shuffle for realism
    rng.shuffle(out)

    out_path = os.path.join(os.path.dirname(__file__), "_synth_dataset.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for row in out:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(out):,} synthetic rows to {out_path}")
    # Distribution summary
    from collections import Counter
    c = Counter()
    for r in out:
        for b in r["expected_buckets"]:
            c[b] += 1
    print("\nBucket distribution (expected):")
    for k, v in c.most_common():
        print(f"  {k}: {v:>4}")


if __name__ == "__main__":
    main()
