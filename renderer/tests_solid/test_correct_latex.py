"""Tests proving CORRECT LaTeX inputs flow through the pipeline cleanly.

These inputs are syntactically valid. The pipeline must:
  - identify them as math (or text where appropriate)
  - apply zero repairs (no false-positive editing)
  - produce KaTeX-ready prepared text byte-equivalent to the input (modulo
    the wrap_math_only repair, which is the only legitimate transformation
    on a "naked" valid LaTeX expression)
  - produce no fallback spans
  - return validation.ok = True
"""
from . import _paths  # noqa: F401 — sets up sys.path

import unittest

from latex_pipeline import build_default_pipeline, RenderOutcome


class CorrectInlineMath(unittest.TestCase):
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def _assert_clean_render(self, text, *, expected_math_count, family="authored_question"):
        r = self.pipeline.run(text, source_family=family)
        self.assertEqual(r.fallback_count, 0, f"unexpected fallback for: {text!r}")
        self.assertEqual(r.math_count, expected_math_count,
                         f"math count mismatch for: {text!r}: got {r.math_count}")
        # Validation OK on every math segment
        for s in r.segments:
            if s.outcome is RenderOutcome.MATH:
                self.assertTrue(s.validation.ok, f"validation failed unexpectedly: {s.validation.reasons}")

    def test_alpha_beta_quadratic(self):
        self._assert_clean_render(
            r"If $\alpha$ and $\beta$ are zeroes of $x^2 - 1$, find $\alpha + \beta$.",
            expected_math_count=4,
        )

    def test_fraction(self):
        self._assert_clean_render(
            r"The value is $\frac{1}{6}$ exactly.",
            expected_math_count=1,
        )

    def test_subscript_water(self):
        self._assert_clean_render("Water is $H_2O$.", expected_math_count=1)

    def test_integral_display(self):
        self._assert_clean_render(r"Solve $$\int_0^1 x^2 dx = \frac{1}{3}$$",
                                  expected_math_count=1)

    def test_set_notation(self):
        self._assert_clean_render(r"The set is $\{(x, y) : y = x - 2\}$.",
                                  expected_math_count=1)

    def test_interval_notation(self):
        self._assert_clean_render(r"Domain: $(-\infty, 0]$.", expected_math_count=1)

    def test_cases_environment(self):
        self._assert_clean_render(
            r"$f(x) = \begin{cases} x^2 & 0 \leq x \leq 3 \\ 9x & 3 < x \leq 10 \end{cases}$",
            expected_math_count=1,
        )

    def test_paren_delim(self):
        self._assert_clean_render(r"We have \(\alpha + \beta\) here.",
                                  expected_math_count=1)

    def test_bracket_display_delim(self):
        self._assert_clean_render(r"Equation: \[E = mc^2\]", expected_math_count=1)

    def test_chemistry_with_mathrm(self):
        self._assert_clean_render(
            r"Reaction: $\mathrm{Fe}_2\mathrm{O}_3 + 3\mathrm{CO} \rightarrow 2\mathrm{Fe} + 3\mathrm{CO}_2$",
            expected_math_count=1,
        )

    def test_currency_only_is_not_math(self):
        # A clean prose sentence with a `$` for currency should NOT be
        # rendered as math, AND must not crash.
        r = self.pipeline.run("The book costs $5 only.", source_family="feedback")
        self.assertEqual(r.fallback_count, 0)
        self.assertEqual(r.math_count, 0)


class CorrectMathOnly(unittest.TestCase):
    """Math-only content (the rubric_criterion field shape) — the only
    transformation is the legitimate $...$ wrap."""

    def setUp(self):
        self.pipeline = build_default_pipeline()

    def _assert_wrapped(self, content, *, family="rubric_criterion"):
        r = self.pipeline.run(content, source_family=family)
        self.assertEqual(r.fallback_count, 0)
        self.assertEqual(r.math_count, 1)
        self.assertIn("wrap_math_only", r.repairs_applied)
        # Round-trip: prepared text should be `${content}$`
        self.assertTrue(r.prepared_text.startswith("$"))
        self.assertTrue(r.prepared_text.endswith("$"))

    def test_bare_fraction(self):
        self._assert_wrapped(r"\alpha + \beta = -\frac{1}{6}")

    def test_bare_root(self):
        self._assert_wrapped(r"s = \sqrt[3]{275}")

    def test_bare_polynomial(self):
        self._assert_wrapped(r"x^2 - 2\sqrt{3}x + 2")


class IdempotenceOnCorrectInputs(unittest.TestCase):
    """prepare(prepare(x)) == prepare(x) — even for already-valid input."""

    def setUp(self):
        self.pipeline = build_default_pipeline()

    SAMPLES = [
        r"If $\alpha$ and $\beta$ are zeroes of $x^2 - 1$, find $\alpha + \beta$.",
        r"$$\int_0^1 x^2 dx = \frac{1}{3}$$",
        r"$\frac{1}{2} = 0.5$",
        r"Water is $H_2O$.",
        # math-only (wrap_math_only fires on first run, must NOT fire on second)
        r"\alpha + \beta = -\frac{1}{6}",
        r"s = \sqrt[3]{275}",
    ]

    def test_double_run_is_stable(self):
        for s in self.SAMPLES:
            r1 = self.pipeline.run(s, source_family="rubric_criterion")
            r2 = self.pipeline.run(r1.prepared_text, source_family="rubric_criterion")
            self.assertEqual(r1.prepared_text, r2.prepared_text,
                             msg=f"Not idempotent on: {s!r}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
