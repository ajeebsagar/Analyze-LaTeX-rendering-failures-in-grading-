"""Auto-heal CLI for the SOLID pipeline.

Usage:
  python -m app.autoheal "  \\alpha + eta = -\\frac{1}{6}  "
  python -m app.autoheal --family rubric_criterion "\\alpha + \\beta = -\\frac{1}{6}"
  echo "broken latex" | python -m app.autoheal
  python -m app.autoheal --file path/to/input.txt
  python -m app.autoheal --interactive
  python -m app.autoheal --quiet "\\alpha + eta"   # for piping
"""
from __future__ import annotations

import argparse
import os
import sys

# Ensure UTF-8 stdout so combining diacritics print on Windows cp1252 consoles
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Path setup so we can run this from anywhere
_here = os.path.dirname(os.path.abspath(__file__))
_src = os.path.join(os.path.dirname(_here), "src")
if _src not in sys.path:
    sys.path.insert(0, _src)

from latex_pipeline import build_default_pipeline, BUCKET_DESCRIPTIONS, RenderOutcome, ErrorAnalyzer


def heal_once(text: str, *, source_family: str, quiet: bool, diagnose: bool = False) -> str:
    pipeline = build_default_pipeline()
    result = pipeline.run(text, source_family=source_family)

    if quiet:
        return result.prepared_text

    print("=" * 72)
    print("INPUT:")
    print(f"  {text!r}")
    print(f"SOURCE FAMILY: {source_family}")

    if diagnose:
        analyzer = ErrorAnalyzer()
        report = analyzer.analyze(text)
        if report.has_errors:
            print()
            print("DIAGNOSTIC — issues detected in the input:")
            for i, issue in enumerate(report.issues, 1):
                print(f"  [{i}] {issue.kind} @ pos {issue.position}")
                if issue.found:     print(f"        found    : {issue.found!r}")
                if issue.missing:   print(f"        missing  : {issue.missing!r}")
                if issue.suggested: print(f"        fix      : {issue.suggested}")
                if issue.context_line:
                    for ln in issue.context_line.splitlines():
                        print(f"        context  | {ln}")
        else:
            print("DIAGNOSTIC: clean — no errors detected.")
    bucket_strs = [f"{b} ({BUCKET_DESCRIPTIONS.get(b, '?')})" for b in result.buckets]
    print(f"BUCKETS MATCHED: {', '.join(bucket_strs) if bucket_strs else '(none)'}")
    if result.repairs_applied:
        print("REPAIRS APPLIED:")
        for r in result.repairs_applied:
            print(f"  - {r}")
    else:
        print("REPAIRS APPLIED: (none)")
    if result.failure_reasons:
        print("VALIDATION:")
        for f in result.failure_reasons:
            print(f"  ! {f}")
    else:
        print("VALIDATION: ok")
    print("HEALED OUTPUT (KaTeX-ready):")
    print(f"  {result.prepared_text}")
    print("SEGMENT TRACE:")
    for i, s in enumerate(result.segments):
        outcome = s.outcome.value
        if s.outcome is RenderOutcome.MATH:
            print(f"  [{i}] {s.kind.value:>13} -> {outcome:<8} | score={s.classification.score:.2f}")
            print(f"       original : {s.original!r}")
            if s.repaired != s.original:
                print(f"       repaired : {s.repaired!r}")
        elif s.outcome is RenderOutcome.FALLBACK:
            print(f"  [{i}] {s.kind.value:>13} -> {outcome:<8} | reasons={s.validation.reasons}")
            print(f"       content  : {s.original!r}")
        else:
            preview = s.original if len(s.original) <= 60 else s.original[:57] + "..."
            print(f"  [{i}] {s.kind.value:>13} -> {outcome:<8} | {preview!r}")
    return result.prepared_text


def main():
    ap = argparse.ArgumentParser(description="Auto-heal broken LaTeX. Prints the KaTeX-ready output.")
    ap.add_argument("text", nargs="?", help="LaTeX text to heal (use --file or stdin if omitted).")
    ap.add_argument("--file", help="Read input from a file.")
    ap.add_argument("--family", default="rubric_criterion",
                    help="Source family (rubric_criterion, ai_solution, feedback, ...). "
                         "Default: rubric_criterion (math-only auto-wrap enabled).")
    ap.add_argument("--quiet", action="store_true", help="Print only the healed string.")
    ap.add_argument("--interactive", action="store_true", help="REPL mode.")
    ap.add_argument("--diagnose", action="store_true",
                    help="Print a pre-parse diagnostic naming which character is missing/wrong.")
    args = ap.parse_args()

    if args.interactive:
        print("Auto-heal interactive mode. Ctrl-C to exit.")
        try:
            while True:
                try:
                    text = input(">>> ")
                except EOFError:
                    break
                if text:
                    heal_once(text, source_family=args.family, quiet=False, diagnose=args.diagnose)
                    print()
        except KeyboardInterrupt:
            print("\nBye.")
        return

    if args.file:
        with open(args.file, "r", encoding="utf-8") as f:
            text = f.read()
    elif args.text is not None:
        text = args.text
    elif not sys.stdin.isatty():
        text = sys.stdin.read()
    else:
        ap.print_help()
        sys.exit(2)

    out = heal_once(text, source_family=args.family, quiet=args.quiet, diagnose=args.diagnose)
    if args.quiet:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
