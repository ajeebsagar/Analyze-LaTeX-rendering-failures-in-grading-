"""Tests for the ErrorAnalyzer: every broken input is pinpointed correctly."""
from . import _paths  # noqa: F401

import unittest

from latex_pipeline import ErrorAnalyzer


class MissingBrace(unittest.TestCase):
    def setUp(self): self.analyzer = ErrorAnalyzer()

    def test_unclosed_frac(self):
        r = self.analyzer.analyze(r"\frac{1}{2")
        # One missing close brace
        kinds = [i.kind for i in r.issues]
        self.assertIn("missing_closing_brace", kinds)
        miss = next(i for i in r.issues if i.kind == "missing_closing_brace")
        # Position points at the OPENING '{' that is unclosed
        self.assertEqual(miss.missing, "}")

    def test_extra_close_brace(self):
        r = self.analyzer.analyze(r"\frac{1}{2}}")
        kinds = [i.kind for i in r.issues]
        self.assertIn("extra_closing_brace", kinds)


class UnbalancedDollar(unittest.TestCase):
    def setUp(self): self.analyzer = ErrorAnalyzer()

    def test_trailing_orphan(self):
        r = self.analyzer.analyze(r"\alpha + \beta$")
        kinds = [i.kind for i in r.issues]
        self.assertIn("unbalanced_dollar", kinds)
        issue = next(i for i in r.issues if i.kind == "unbalanced_dollar")
        # Position is the orphan $ (the only one)
        self.assertEqual(issue.position, len(r.original_text) - 1)

    def test_balanced_dollars_are_ok(self):
        r = self.analyzer.analyze(r"$\alpha$ and $\beta$")
        self.assertFalse(any(i.kind == "unbalanced_dollar" for i in r.issues))


class OrphanBackslash(unittest.TestCase):
    def setUp(self): self.analyzer = ErrorAnalyzer()

    def test_eta_orphan(self):
        r = self.analyzer.analyze(r"\alpha + eta = 5")
        issue = next(i for i in r.issues if i.kind == "orphan_backslash" and i.found == "eta")
        self.assertEqual(issue.missing, "\\")
        self.assertIn(r"\beta", issue.suggested)

    def test_rac_orphan(self):
        r = self.analyzer.analyze(r"x = rac{1}{2}")
        issue = next(i for i in r.issues if i.found == "rac")
        self.assertEqual(issue.missing, "\\")
        self.assertIn(r"\frac", issue.suggested)


class FillBlank(unittest.TestCase):
    def setUp(self): self.analyzer = ErrorAnalyzer()
    def test_underscore_run(self):
        r = self.analyzer.analyze("Element is ______")
        self.assertTrue(any(i.kind == "fill_blank_subscript_run" for i in r.issues))


class ForbiddenCommand(unittest.TestCase):
    def setUp(self): self.analyzer = ErrorAnalyzer()
    def test_input_command(self):
        r = self.analyzer.analyze(r"\input{passwd}")
        self.assertTrue(any(i.kind == "forbidden_command" for i in r.issues))


class CombiningDiacritic(unittest.TestCase):
    def setUp(self): self.analyzer = ErrorAnalyzer()
    def test_diacritic_detected(self):
        r = self.analyzer.analyze("\\alpha + \\beta + ̑\\alpha")
        self.assertTrue(any(i.kind == "combining_diacritic" for i in r.issues))


class CleanInput(unittest.TestCase):
    def setUp(self): self.analyzer = ErrorAnalyzer()
    def test_clean_text_has_no_issues(self):
        r = self.analyzer.analyze(r"$\frac{1}{2} + \alpha$")
        self.assertFalse(r.has_errors)


class CompoundIssues(unittest.TestCase):
    """The user's exact input — missing $ AND missing backslash on \\beta."""
    def setUp(self): self.analyzer = ErrorAnalyzer()
    def test_users_input(self):
        r = self.analyzer.analyze(r"\alpha + eta = -\frac{1}{6}$")
        kinds = [i.kind for i in r.issues]
        self.assertIn("unbalanced_dollar", kinds)
        self.assertIn("orphan_backslash", kinds)


if __name__ == "__main__":
    unittest.main(verbosity=2)
