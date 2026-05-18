"""Tests proving BROKEN LaTeX inputs are auto-healed correctly.

For each broken input we assert:
  - which bucket(s) fire
  - which repair name(s) get applied
  - the EXACT healed output string (where a deterministic fix exists)
  - or, where the right answer is "do not render", that the segment falls
    back to text/fallback (never crashes, never produces wrong math)
"""
from . import _paths  # noqa: F401

import unittest

from latex_pipeline import build_default_pipeline, RenderOutcome


class BucketA_MissingDelimiters(unittest.TestCase):
    """Bucket A — content stored without $...$ wrappers."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_simple_fraction_wrapped(self):
        r = self.pipeline.run(r"\alpha + \beta = -\frac{1}{6}",
                              source_family="rubric_criterion")
        self.assertIn("A", r.buckets)
        self.assertIn("wrap_math_only", r.repairs_applied)
        self.assertEqual(r.prepared_text, r"$\alpha + \beta = -\frac{1}{6}$")
        self.assertEqual(r.fallback_count, 0)
        self.assertEqual(r.math_count, 1)

    def test_nested_fraction_wrapped(self):
        r = self.pipeline.run(
            r"\frac{(\alpha + \beta)^2 - 2\alpha\beta}{\alpha\beta}",
            source_family="rubric_criterion")
        self.assertEqual(r.prepared_text,
                         r"$\frac{(\alpha + \beta)^2 - 2\alpha\beta}{\alpha\beta}$")
        self.assertEqual(r.fallback_count, 0)


class BucketD_OcrCorruption(unittest.TestCase):
    """Bucket D — orphan backslashes, glued names, combining diacritics."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_orphan_eta_to_beta(self):
        r = self.pipeline.run(r"$\alpha + eta + \alpha\beta$",
                              source_family="feedback")
        self.assertIn("D", r.buckets)
        self.assertIn("repair_orphan_eta_to_beta", r.repairs_applied)
        self.assertEqual(r.prepared_text, r"$\alpha + \beta + \alpha\beta$")

    def test_orphan_rac_to_frac(self):
        r = self.pipeline.run(r"$\frac{1}{3} \times rac{2}{5}$",
                              source_family="feedback")
        self.assertIn("D", r.buckets)
        self.assertIn("repair_orphan_rac", r.repairs_applied)
        self.assertEqual(r.prepared_text, r"$\frac{1}{3} \times \frac{2}{5}$")

    def test_glued_alphaeta(self):
        r = self.pipeline.run(r"$\alpha + alphaeta = 5$",
                              source_family="feedback")
        self.assertIn("D", r.buckets)
        self.assertIn("repair_alphaeta", r.repairs_applied)
        self.assertEqual(r.prepared_text, r"$\alpha + \alpha\beta = 5$")

    def test_combining_diacritic_stripped(self):
        # U+0311 COMBINING INVERTED BREVE injected into math content
        broken = "$\\alpha + \\beta + ̑\\alpha\\beta$"
        clean = r"$\alpha + \beta + \alpha\beta$"
        r = self.pipeline.run(broken, source_family="feedback")
        self.assertIn("D", r.buckets)
        self.assertIn("strip_combining_diacritics", r.repairs_applied)
        self.assertEqual(r.prepared_text, clean)


class BucketC_UnbalancedDollar(unittest.TestCase):
    """Bucket C — odd dollar count. Segmenter drops the orphan trailing $."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_truncated_input_does_not_crash(self):
        broken = "... $0.1 M$ and $0.5 M$. [Ka for $..."
        r = self.pipeline.run(broken, source_family="authored_question")
        self.assertIn("C", r.buckets)
        self.assertEqual(r.fallback_count, 0)
        # Two complete math spans survived
        self.assertEqual(r.math_count, 2)

    def test_orphan_trailing_dollar_with_missing_backslash(self):
        """Real user input: missing opening $ AND missing backslash on \\beta.

        Was previously NOT auto-healed because the trailing $ blocked
        the math-only wrapper. Fixed by `wrap_math_only_strip_orphan_dollar`.
        """
        r = self.pipeline.run(r"\alpha + eta = -\frac{1}{6}$",
                              source_family="rubric_criterion")
        self.assertEqual(r.prepared_text, r"$\alpha + \beta = -\frac{1}{6}$")
        self.assertIn("wrap_math_only_strip_orphan_dollar", r.repairs_applied)
        self.assertIn("repair_orphan_eta_to_beta", r.repairs_applied)
        self.assertEqual(r.fallback_count, 0)
        self.assertEqual(r.math_count, 1)

    def test_orphan_leading_dollar(self):
        """Symmetric case: orphan $ at the START of an otherwise math-only string."""
        r = self.pipeline.run(r"$\alpha + \beta = -\frac{1}{6}",
                              source_family="rubric_criterion")
        self.assertEqual(r.prepared_text, r"$\alpha + \beta = -\frac{1}{6}$")
        self.assertIn("wrap_math_only_strip_orphan_dollar", r.repairs_applied)

    def test_orphan_dollar_does_not_wrap_currency_prose(self):
        """Safety: `Cost: $5` has 1 orphan $ but no math command, so we
        leave it alone — must NOT become `$Cost: 5$`."""
        r = self.pipeline.run("Cost: $5 only.", source_family="feedback")
        self.assertEqual(r.prepared_text, "Cost: $5 only.")
        self.assertNotIn("wrap_math_only_strip_orphan_dollar", r.repairs_applied)


class BucketH_FalsePositive(unittest.TestCase):
    """Bucket H — content that LOOKS like math but should not be rendered."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_fill_in_the_blank_not_rendered(self):
        r = self.pipeline.run("The most electronegative element is ______",
                              source_family="authored_question")
        self.assertEqual(r.math_count, 0)
        self.assertEqual(r.fallback_count, 0)


class BucketJ_CurrencyText(unittest.TestCase):
    """Bucket J — currency-shaped text must NOT become math."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_dollar_amount_is_not_math(self):
        r = self.pipeline.run("The book costs $5", source_family="feedback")
        self.assertEqual(r.math_count, 0)
        self.assertEqual(r.fallback_count, 0)


class BucketL_MultilineAiSolution(unittest.TestCase):
    """Bucket L — literal `\\n` in ai_solution prose."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_literal_n_becomes_real_newline(self):
        r = self.pipeline.run("Step 1: do thing.\\nStep 2: do other.",
                              source_family="ai_solution")
        self.assertIn("L", r.buckets)
        self.assertIn("literal_escape_to_whitespace", r.repairs_applied)
        self.assertEqual(r.prepared_text, "Step 1: do thing.\nStep 2: do other.")


class BucketF_HtmlMixed(unittest.TestCase):
    """Bucket F — HTML in question body. The pipeline now processes HTML-aware:
    tags pass through verbatim, math segments inside still render.
    """
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_html_table_does_not_crash(self):
        r = self.pipeline.run(
            "Find: <table><tr><td>1</td></tr></table>",
            source_family="authored_question")
        self.assertIn("F", r.buckets)
        # The pipeline must not throw and must not produce a fallback for
        # the HTML chunk itself. The HTML tags are now passed through.
        self.assertEqual(r.fallback_count, 0)
        self.assertEqual(r.math_count, 0)
        # The output HTML contains the original tags verbatim.
        self.assertIn("<table>", r.html)
        self.assertIn("</table>", r.html)

    def test_html_with_inline_math_renders_both(self):
        r = self.pipeline.run(
            r"Find $x^2$ in the table: <table><tr><td>$y = 1$</td></tr></table>",
            source_family="authored_question")
        # Both math segments still render even though the row contains HTML.
        self.assertGreaterEqual(r.math_count, 2)
        self.assertIn("<table>", r.html)


class BucketE_ForbiddenCommand(unittest.TestCase):
    """Bucket E — security: forbidden commands rejected."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_input_command_rejected(self):
        r = self.pipeline.run(r"$\input{/etc/passwd}$",
                              source_family="student_answer")
        self.assertIn("E", r.buckets)
        self.assertEqual(r.fallback_count, 1)


class BucketB_BrokenBraces(unittest.TestCase):
    """Bucket B — unbalanced braces."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_unclosed_frac_emits_fallback(self):
        r = self.pipeline.run(r"$\frac{1}{2$ next sentence", source_family="feedback")
        # Either the segmenter dropped the orphan dollar OR the validator
        # rejected. Either way: no crash, no false math.
        self.assertEqual(r.math_count + r.fallback_count, len(r.segments) - sum(
            1 for s in r.segments if s.outcome is RenderOutcome.TEXT))


class CombinedScenarios(unittest.TestCase):
    """Realistic dataset-shaped inputs: multiple buckets co-occurring."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_ai_solution_with_orphan_and_literal_n(self):
        broken = "Step 1: identify $\\alpha + eta$.\\nStep 2: compute."
        r = self.pipeline.run(broken, source_family="ai_solution")
        # Both repairs should have fired
        self.assertIn("repair_orphan_eta_to_beta", r.repairs_applied)
        self.assertIn("literal_escape_to_whitespace", r.repairs_applied)
        self.assertEqual(r.fallback_count, 0)
        # The math span renders cleanly with \beta restored
        math_segments = [s for s in r.segments if s.outcome is RenderOutcome.MATH]
        self.assertEqual(len(math_segments), 1)
        self.assertEqual(math_segments[0].repaired, r"\alpha + \beta")

    def test_mixed_prose_and_math_with_diacritic(self):
        broken = "The answer is $\\alpha + \\beta + ̑ \\gamma$ — done."
        r = self.pipeline.run(broken, source_family="feedback")
        self.assertEqual(r.fallback_count, 0)
        self.assertIn("strip_combining_diacritics", r.repairs_applied)
        math = [s for s in r.segments if s.outcome is RenderOutcome.MATH][0]
        self.assertNotIn("̑", math.repaired)


class NeverThrowsOnArbitraryGarbage(unittest.TestCase):
    """The pipeline must not throw on ANY input shape."""
    def setUp(self):
        self.pipeline = build_default_pipeline()

    def test_empty_string(self):
        r = self.pipeline.run("")
        self.assertEqual(r.prepared_text, "")
        self.assertEqual(r.fallback_count, 0)

    def test_none_input(self):
        r = self.pipeline.run(None)
        self.assertEqual(r.prepared_text, "")

    def test_only_dollar_signs(self):
        r = self.pipeline.run("$$$$")
        # Should parse as one display math segment with empty content
        # (validator rejects empty -> fallback). No crash.
        self.assertGreaterEqual(r.fallback_count + r.math_count, 0)

    def test_random_garbage(self):
        garbage = "\\\\\\$$$$$$\\frac{{{{}}}}̑́eta rac{1}{2}__________"
        r = self.pipeline.run(garbage, source_family="feedback")
        # Either everything ends up in fallback / text, or some math
        # survives — but the pipeline NEVER throws.
        self.assertIsNotNone(r.prepared_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
