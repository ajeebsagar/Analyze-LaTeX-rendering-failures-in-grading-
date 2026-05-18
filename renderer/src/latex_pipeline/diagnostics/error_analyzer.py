"""ErrorAnalyzer — pinpoints WHICH character is missing or wrong in a LaTeX
string, BEFORE handing it to KaTeX.

Returns a structured ErrorReport listing every issue with:
  - kind         (missing_brace, missing_dollar, orphan_backslash, ...)
  - position     (0-based offset in the original text)
  - missing      (the character or string that should be inserted)
  - found        (what was found instead, or None)
  - suggested    (the literal repair string)
  - context_line (one-line snippet with a caret pointing at the issue)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List


# ---- Public dataclasses ----

@dataclass
class ErrorIssue:
    kind: str            # 'missing_brace' | 'unbalanced_dollar' | 'orphan_backslash'
                          # | 'fill_blank' | 'forbidden_command' | 'combining_diacritic'
    position: int        # 0-based offset in the original text
    missing: str = ""    # what should be inserted (e.g. '}' or '\\')
    found: str = ""      # what was found instead (e.g. 'EOF' or 'eta')
    suggested: str = ""  # human-readable fix description
    context_line: str = ""  # snippet with a caret marker

    def __str__(self) -> str:
        head = f"[{self.kind} @ position {self.position}]"
        bits = []
        if self.found: bits.append(f"found={self.found!r}")
        if self.missing: bits.append(f"missing={self.missing!r}")
        return f"{head}  " + "  ".join(bits)


@dataclass
class ErrorReport:
    original_text: str
    issues: List[ErrorIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return bool(self.issues)

    def format_report(self) -> str:
        if not self.issues:
            return "No errors detected — KaTeX should render this cleanly."
        lines = [f"Analysis of: {self.original_text!r}", ""]
        for i, issue in enumerate(self.issues, 1):
            lines.append(f"ISSUE {i}: {issue.kind}")
            lines.append(f"  position    : {issue.position}")
            if issue.found:
                lines.append(f"  found       : {issue.found!r}")
            if issue.missing:
                lines.append(f"  missing     : {issue.missing!r}")
            if issue.suggested:
                lines.append(f"  fix         : {issue.suggested}")
            if issue.context_line:
                lines.append(f"  context     : {issue.context_line}")
            lines.append("")
        return "\n".join(lines)


# ---- Analyzer ----

class ErrorAnalyzer:
    """Pre-parse diagnostic. Detects everything the SOLID pipeline knows how
    to fix, plus issues that would cause a KaTeX ParseError.
    """

    # Patterns mirror the repair regexes so the diagnostic matches what the
    # autoheal will actually fix.
    _ORPHAN_PATTERNS = {
        "eta":      (re.compile(r"(?<![\\A-Za-z])eta\b"),         r"\beta",   "\\"),
        "rac":      (re.compile(r"(?<![A-Za-z])rac\{"),           r"\frac",   "\\"),
        "ext":      (re.compile(r"(?<![\\A-Za-z])ext\{"),         r"\text",   "\\"),
        "alphaeta": (re.compile(r"(?<![\\A-Za-z])alphaeta\b"),    r"\alpha\beta", "\\ + restructure"),
    }
    _FORBIDDEN = re.compile(r"\\(input|include|write|openout|csname|loop|repeat|href|url|includegraphics)\b")
    _FILL_BLANK = re.compile(r"_{3,}")
    _COMBINING = re.compile(r"[̀-ͯ]")

    def analyze(self, text: str) -> ErrorReport:
        issues: List[ErrorIssue] = []

        # 1. Brace balance — track WHICH brace is missing
        issues.extend(self._check_braces(text))

        # 2. Unescaped dollar parity
        issues.extend(self._check_dollars(text))

        # 3. Orphan backslash family (eta, rac, ext, alphaeta)
        issues.extend(self._check_orphan_backslashes(text))

        # 4. Combining diacritic in math context
        issues.extend(self._check_combining_diacritic(text))

        # 5. Fill-in-the-blank subscript runs
        issues.extend(self._check_fill_blank(text))

        # 6. Forbidden commands (security)
        issues.extend(self._check_forbidden_commands(text))

        return ErrorReport(original_text=text, issues=issues)

    # ----- Individual checks -----

    def _check_braces(self, text: str) -> List[ErrorIssue]:
        """Walk the string. Track open-brace positions in a stack so we can
        point at the brace that was never closed."""
        out: List[ErrorIssue] = []
        stack: List[int] = []
        i = 0
        n = len(text)
        while i < n:
            c = text[i]
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "{":
                stack.append(i)
            elif c == "}":
                if not stack:
                    out.append(ErrorIssue(
                        kind="extra_closing_brace",
                        position=i,
                        found="}",
                        missing="(matching '{' earlier in string)",
                        suggested=f"Remove the '}}' at position {i}, OR insert a matching '{{' before it.",
                        context_line=self._context_marker(text, i),
                    ))
                else:
                    stack.pop()
            i += 1

        for open_pos in stack:
            out.append(ErrorIssue(
                kind="missing_closing_brace",
                position=open_pos,
                found="EOF",
                missing="}",
                suggested=f"Insert '}}' to close the '{{' opened at position {open_pos}.",
                context_line=self._context_marker(text, open_pos),
            ))
        return out

    def _check_dollars(self, text: str) -> List[ErrorIssue]:
        """Find unescaped $ characters. If count is odd, flag the orphan."""
        positions: List[int] = []
        i = 0
        n = len(text)
        while i < n:
            c = text[i]
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "$":
                positions.append(i)
            i += 1
        if len(positions) % 2 == 0:
            return []
        # The orphan: by convention we flag the LAST one (most often the
        # truncation case). The autoheal strips this orphan.
        orphan = positions[-1]
        return [ErrorIssue(
            kind="unbalanced_dollar",
            position=orphan,
            found="$",
            missing="(matching '$' delimiter)",
            suggested=("Strip the orphan '$' (truncation) OR insert a matching "
                       "'$' to close the math segment."),
            context_line=self._context_marker(text, orphan),
        )]

    def _check_orphan_backslashes(self, text: str) -> List[ErrorIssue]:
        out: List[ErrorIssue] = []
        for name, (pat, replacement, missing_char) in self._ORPHAN_PATTERNS.items():
            for m in pat.finditer(text):
                out.append(ErrorIssue(
                    kind="orphan_backslash",
                    position=m.start(),
                    found=name,
                    missing=missing_char,
                    suggested=f"Replace {name!r} with {replacement!r} (likely a lost backslash).",
                    context_line=self._context_marker(text, m.start()),
                ))
        return out

    def _check_combining_diacritic(self, text: str) -> List[ErrorIssue]:
        out: List[ErrorIssue] = []
        for m in self._COMBINING.finditer(text):
            out.append(ErrorIssue(
                kind="combining_diacritic",
                position=m.start(),
                found=f"U+{ord(m.group(0)):04X}",
                missing="",
                suggested="Strip this combining diacritic; it cannot appear inside math.",
                context_line=self._context_marker(text, m.start()),
            ))
        return out

    def _check_fill_blank(self, text: str) -> List[ErrorIssue]:
        out: List[ErrorIssue] = []
        for m in self._FILL_BLANK.finditer(text):
            out.append(ErrorIssue(
                kind="fill_blank_subscript_run",
                position=m.start(),
                found=m.group(0),
                missing="",
                suggested=("Underscore run is a fill-in-the-blank marker, not math. "
                           "Render as plain text."),
                context_line=self._context_marker(text, m.start()),
            ))
        return out

    def _check_forbidden_commands(self, text: str) -> List[ErrorIssue]:
        out: List[ErrorIssue] = []
        for m in self._FORBIDDEN.finditer(text):
            out.append(ErrorIssue(
                kind="forbidden_command",
                position=m.start(),
                found=m.group(0),
                missing="",
                suggested="This command is blocked for security. The renderer falls back to text.",
                context_line=self._context_marker(text, m.start()),
            ))
        return out

    # ----- Helpers -----

    @staticmethod
    def _context_marker(text: str, position: int, width: int = 28) -> str:
        """Produce a snippet of the text with a caret line pointing at `position`.

        Returns two lines separated by `\\n`:
          line 1: a window of the original text around the position
          line 2: spaces + a `^` indicating the column of the issue

        The caller is expected to print each line with the same left-margin.
        """
        start = max(0, position - width)
        end = min(len(text), position + width)
        snippet = text[start:end].replace("\n", " ")
        caret = " " * (position - start) + "^"
        return snippet + "\n" + caret
