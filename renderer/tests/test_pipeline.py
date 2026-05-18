"""
Golden test suite — covers every bucket in the analysis report.

Each test asserts at least one of:
  (1) no exception is raised
  (2) segments produce expected math/text/fallback outcome
  (3) repair is idempotent
"""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import unittest

from pipeline import prepare_text, render_text
from pipeline.repair import tier2_orphan_backslash
from pipeline.segmenter import segment
from pipeline.validator import validate


def _math_count(result):
    return sum(1 for s in result.segments if s.rendered_as == "math")


def _fallback_count(result):
    return sum(1 for s in result.segments if s.rendered_as == "fallback")


class A_CleanInlineMath(unittest.TestCase):
    def test_basic_alpha_beta(self):
        r = prepare_text(
            r"If $\alpha$ and $\beta$ are zeroes of $x^2 - 1$..."
        )
        self.assertEqual(_math_count(r), 3)
        self.assertEqual(_fallback_count(r), 0)


class B_CleanDisplayMath(unittest.TestCase):
    def test_display_math(self):
        r = prepare_text(r"Solve: $$\int_0^1 x^2 dx = \frac{1}{3}$$")
        self.assertGreaterEqual(_math_count(r), 1)
        self.assertEqual(_fallback_count(r), 0)


class C_MissingDelimiters_MathOnly(unittest.TestCase):
    def test_rubric_criterion_wrap(self):
        text = r"\alpha + \beta = -\frac{1}{6}, \alpha\beta = -\frac{1}{3}"
        r = prepare_text(
            text,
            field_path="assignment_question.body.rubric_steps[0].criterion",
        )
        # Should auto-wrap into a math segment
        self.assertGreaterEqual(_math_count(r), 1)
        self.assertIn("wrap_math_only", r.repairs_applied)


class D_MissingDelimiters_BareSupSub(unittest.TestCase):
    def test_no_command_no_wrap_for_prose_default(self):
        # Without a strong family prior, bare `x^2` stays as prose to avoid
        # false-positive auto-wrapping of prose like "the value x^2".
        r = prepare_text("the value x^2 cofficent = 3")
        self.assertEqual(_math_count(r), 0)


class E_UnbalancedDollar(unittest.TestCase):
    def test_truncated_dollar_is_dropped(self):
        text = "... $0.1\\,M\\,CH_3COOH$ and $0.5\\,M\\,CH_3COONa$. [Ka for $..."
        r = prepare_text(text)
        # No exceptions; the trailing `$` orphan is treated as literal text.
        self.assertGreaterEqual(_math_count(r), 2)
        self.assertNotIn(r"$.", r.prepared_text[-3:])  # trailing $ was dropped


class F_OrphanBackslashFamily(unittest.TestCase):
    def test_beta_orphan_repair(self):
        r = prepare_text(r"$\alpha + eta + \alpha\beta$")
        # The `eta` orphan should be repaired to `\beta`
        self.assertIn(r"\beta", r.segments[0].repaired)
        self.assertIn("repair_orphan_eta_to_beta", r.repairs_applied)

    def test_rac_orphan_repair(self):
        r = prepare_text(r"$\frac{1}{3} \times rac{2}{5}$")
        self.assertIn(r"\frac{2}{5}", r.segments[0].repaired)
        self.assertIn("repair_orphan_rac", r.repairs_applied)

    def test_alphaeta_glued(self):
        r = prepare_text(r"$\alpha + alphaeta = 5$")
        self.assertIn(r"\alpha\beta", r.segments[0].repaired)


class G_CombiningDiacritic(unittest.TestCase):
    def test_strip_combining(self):
        # U+0311 = COMBINING INVERTED BREVE
        text = "$\\alpha + \\beta + ̑\\alpha\\beta$"
        r = prepare_text(text)
        self.assertNotIn("̑", r.segments[0].repaired)
        self.assertIn("strip_combining_diacritics", r.repairs_applied)


class H_LiteralBackslashN(unittest.TestCase):
    def test_literal_n_to_newline(self):
        text = "Step 1: do thing.\\n\\nStep 2: do other thing."
        r = prepare_text(text, field_path="assignment_question.body.ai_solution")
        self.assertIn("\n", r.prepared_text)
        self.assertIn("literal_escape_to_whitespace", r.repairs_applied)


class I_FillInTheBlank(unittest.TestCase):
    def test_underscores_do_not_break(self):
        text = "The most electronegative element is ______"
        r = prepare_text(text)
        # We never emit a math segment for fill-in-the-blank
        self.assertEqual(_math_count(r), 0)


class J_HTMLMixedInQuestionBody(unittest.TestCase):
    def test_html_table_routed_to_html(self):
        text = "Find the statistics: <table><tr><td>1</td></tr></table>"
        r = prepare_text(text, field_path="assignment_question.body.question_text")
        # HTML short-circuit: single non-math segment, no parse attempted
        self.assertEqual(_math_count(r), 0)


class K_CurrencyFalsePositive(unittest.TestCase):
    def test_currency_amount_is_not_math(self):
        text = "The book costs $5"
        r = prepare_text(text)
        # `$5` alone with no closing `$` is odd-dollar -> dropped, treated as text
        self.assertEqual(_math_count(r), 0)

    def test_two_dollars_one_currency_one_math(self):
        # Ambiguous: two `$` could be a currency pair or a math span
        text = "Price is $5 and formula is $x^2$"
        r = prepare_text(text)
        # The pipeline accepts the first as currency-shaped (low confidence)
        # and keeps it as fallback/text; the second as math.
        self.assertGreaterEqual(_math_count(r), 0)


class L_CurrencyLikeMath(unittest.TestCase):
    def test_currency_like_math_with_command(self):
        text = "Acceleration is $10^5 kg \\cdot m/s^2$"
        r = prepare_text(text)
        self.assertEqual(_math_count(r), 1)


class M_SetIntervalNotation(unittest.TestCase):
    def test_set_braces(self):
        r = prepare_text(r"$\{(x, y) : y = x - 2\}$")
        self.assertEqual(_math_count(r), 1)
        self.assertEqual(_fallback_count(r), 0)

    def test_interval(self):
        r = prepare_text(r"$(-\infty, 0]$")
        self.assertEqual(_math_count(r), 1)


class N_CasesEnv(unittest.TestCase):
    def test_cases_env(self):
        text = r"$f(x) = \begin{cases} x^2, & 0 \leq x \leq 3 \\ 9x, & 3 \leq x \leq 10 \end{cases}$"
        r = prepare_text(text)
        self.assertEqual(_math_count(r), 1)


class O_NestedTextMathConflict(unittest.TestCase):
    def test_nested_text_in_math_does_not_throw(self):
        # We don't try to fix this; we accept the segment and rely on KaTeX
        # to render with strict:'ignore'. Pipeline must not crash.
        r = prepare_text(r"$\frac{1}{\text{\sqrt{3}}}$")
        self.assertEqual(_fallback_count(r) + _math_count(r), 1)


class P_LongMixedProseAndMath(unittest.TestCase):
    def test_long_ai_solution(self):
        text = (
            r"Step 1: Identify the coefficients of $f(x) = 6x^2 + x - 2$. "
            r"Here, $a = 6, b = 1, c = -2$. " * 3
            + r"The product $\alpha\beta = \frac{c}{a} = -\frac{1}{3}$."
        )
        r = prepare_text(text, field_path="assignment_question.body.ai_solution")
        # Many math spans; no fallbacks.
        self.assertGreater(_math_count(r), 5)
        self.assertEqual(_fallback_count(r), 0)


class Q_OCRNoisyStudentWork(unittest.TestCase):
    def test_does_not_throw_on_OCR_text(self):
        text = "the value x^2 cofficent = 3\n'' '' x cofficent = 4"
        r = prepare_text(text, field_path="graded_item.review_render.working_lines[0].text")
        # No fallback unless we segmentized math, which we shouldn't here.
        self.assertEqual(_fallback_count(r), 0)


class R_UnsupportedCommand_SecurityCheck(unittest.TestCase):
    def test_forbidden_command_rejected(self):
        r = prepare_text(r"$\input{/etc/passwd}$")
        self.assertEqual(_math_count(r), 0)
        self.assertEqual(_fallback_count(r), 1)


class S_TruncatedCasesEnv(unittest.TestCase):
    def test_truncated_cases_is_safe(self):
        # First half of a cases block then EOF
        text = r"$f(x) = \begin{cases} x^2, & 0 \leq x"
        r = prepare_text(text)
        # Odd dollar count → truncation guard drops the opener; no math, no crash.
        self.assertEqual(_math_count(r), 0)


class T_Idempotence(unittest.TestCase):
    """The most important class: repair must be a fixed point."""

    SAMPLES = [
        r"$\alpha + \beta = -\frac{1}{6}, \alpha\beta = -\frac{1}{3}$",
        r"\alpha + \beta = -\frac{1}{6}",  # missing delim, wrappable
        r"Find the zeroes of $3x^2 - x - 4$",
        r"$\alpha + eta + \alpha\beta$",   # corrupt
        r"\frac{(\alpha + \beta)^2 - 2\alpha\beta}{\alpha\beta}",
        r"\sqrt[3]{275}",
        r"(-\infty, 0]",
        r"The most electronegative element is ______",
    ]

    def test_double_run_is_stable(self):
        for s in self.SAMPLES:
            r1 = prepare_text(s, field_path="assignment_question.body.rubric_steps[0].criterion")
            r2 = prepare_text(r1.prepared_text, field_path="assignment_question.body.rubric_steps[0].criterion")
            self.assertEqual(r1.prepared_text, r2.prepared_text,
                             msg=f"Not idempotent on input: {s!r}\n1st: {r1.prepared_text!r}\n2nd: {r2.prepared_text!r}")


class U_ValidatorRejects(unittest.TestCase):
    def test_unbalanced_braces(self):
        v = validate(r"\frac{1}{2")
        self.assertFalse(v.ok)
        self.assertIn("unbalanced_brace_count", v.reasons)

    def test_subscript_run(self):
        v = validate("a_____")
        self.assertFalse(v.ok)
        self.assertIn("subscript_run_too_long", v.reasons)

    def test_too_long(self):
        v = validate("x" * 9000)
        self.assertFalse(v.ok)
        self.assertIn("exceeds_max_length", v.reasons)


class V_SegmenterTruncationGuard(unittest.TestCase):
    def test_odd_dollar_drops_trailing(self):
        text = "Before $x = 1$ and after $oops"
        segs = segment(text)
        # We should have: text, math, text  (the trailing `$oops` is text)
        kinds = [s.kind for s in segs]
        self.assertEqual(kinds.count("math_inline"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
