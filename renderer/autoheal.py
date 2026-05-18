"""
Auto-heal CLI.

Usage:
  python autoheal.py "  \\alpha + eta = -\\frac{1}{6}  "
  python autoheal.py --family rubric_criterion "\\alpha + \\beta = -\\frac{1}{6}"
  echo "broken latex" | python autoheal.py
  python autoheal.py --file path/to/input.txt
  python autoheal.py --interactive

Output: a clean prepared string ready for KaTeX, plus a trace of repairs and
the matched failure buckets.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pipeline import prepare_text, label_buckets, BUCKET_DESCRIPTIONS
from pipeline.classifier import family_of


def heal(text: str, *, source_family: str = "rubric_criterion", quiet: bool = False) -> str:
    """
    The one-line API: heal an arbitrary string and return the prepared text.
    `source_family` defaults to `rubric_criterion` so that math-only inputs
    are automatically wrapped in `$...$`.
    """
    result = prepare_text(text, source_family=source_family)
    if quiet:
        return result.prepared_text

    buckets = label_buckets(text, result)
    bucket_names = [f"{b}({BUCKET_DESCRIPTIONS[b]})" for b in buckets]
    print("=" * 70)
    print("INPUT:")
    print(f"  {text!r}")
    print("BUCKETS MATCHED:")
    print(f"  {', '.join(bucket_names) if bucket_names else '(none)'}")
    print("REPAIRS APPLIED:")
    if result.repairs_applied:
        for r in result.repairs_applied:
            print(f"  - {r}")
    else:
        print("  (none)")
    print("VALIDATION:")
    if result.failure_reasons:
        for f in result.failure_reasons:
            print(f"  ! {f}")
    else:
        print("  ok")
    print("HEALED OUTPUT (prepared for KaTeX):")
    print(f"  {result.prepared_text}")
    print("SEGMENT TRACE:")
    for i, s in enumerate(result.segments):
        if s.rendered_as == "math":
            print(f"  [{i}] {s.kind:>13} -> {s.rendered_as:<9} | score={s.classification.score:.2f}")
            print(f"       original:  {s.original!r}")
            if s.repaired != s.original:
                print(f"       repaired:  {s.repaired!r}")
        elif s.rendered_as == "fallback":
            print(f"  [{i}] {s.kind:>13} -> FALLBACK | reasons={s.validation_reasons}")
            print(f"       content:   {s.original!r}")
        else:
            preview = s.original if len(s.original) <= 60 else s.original[:57] + "..."
            print(f"  [{i}] {s.kind:>13} -> {s.rendered_as:<9} | {preview!r}")
    return result.prepared_text


def main():
    ap = argparse.ArgumentParser(description="Auto-heal a broken LaTeX string and print the prepared (KaTeX-ready) output.")
    ap.add_argument("text", nargs="?", help="LaTeX text to heal. If omitted, read from stdin or --file.")
    ap.add_argument("--file", help="Read input from file.")
    ap.add_argument("--family", default="rubric_criterion",
                    help="Source family prior (rubric_criterion, ai_solution, student_answer, etc.). "
                         "Default: rubric_criterion (math-only auto-wrap enabled).")
    ap.add_argument("--quiet", action="store_true", help="Print only the healed prepared string.")
    ap.add_argument("--interactive", action="store_true", help="Read repeated inputs from stdin in a loop.")
    args = ap.parse_args()

    if args.interactive:
        print("Auto-heal interactive mode. Paste a line and press Enter. Ctrl-C to exit.")
        try:
            while True:
                try:
                    text = input(">>> ")
                except EOFError:
                    break
                if not text:
                    continue
                heal(text, source_family=args.family, quiet=False)
                print()
        except KeyboardInterrupt:
            print("\nBye.")
        return

    # Resolve input source
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

    out = heal(text, source_family=args.family, quiet=args.quiet)
    if args.quiet:
        sys.stdout.write(out)


if __name__ == "__main__":
    main()
