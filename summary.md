# Sanitized LaTeX Rendering Dataset

Generated from all tenant DB/S3 assignment and grading text fields.

Client names, tenant labels, assignment titles, sections, trace IDs, emails, phone numbers, URLs, and S3 paths have been replaced with neutral labels/placeholders.

Total candidate text rows: 467886

## Files

- `all_candidates.jsonl`: sanitized raw extracted candidate text rows.
- `classified_candidates.jsonl`: sanitized full row-level classification.
- `labeled_sample.csv`: capped diverse sample by category.
- `confirmed_broken.csv`: rows likely to break or render as raw LaTeX.
- `confirmed_good.csv`: rows whose explicit LaTeX rendered cleanly.
- `tricky_examples.csv`: dollar/currency/false-positive style rows.
- `golden_test_set.csv`: smaller handoff set for renderer behavior review.
- `classification_summary.json`: machine-readable counts.
- `extraction_summary.json`: tenant extraction coverage with anonymized tenant labels.

## Category Counts

- renders_correctly: 190167
- plain_text_no_math: 167417
- likely_math_missing_delimiters: 54041
- missing_math_delimiters: 38387
- tricky_false_positive: 16524
- bad_brace_balance: 804
- unbalanced_dollar: 192
- katex_parse_error: 151
- latex_parse_error: 125
- bad_super_or_subscript: 30
- html_or_markdown_mixed_text: 25
- unsupported_latex_command: 18
- display_or_mode_conflict: 5

## Tenant Counts

- tenant_006: 233990
- tenant_004: 123325
- tenant_012: 38058
- tenant_001: 36496
- tenant_010: 23035
- tenant_007: 7796
- tenant_003: 2623
- tenant_011: 804
- tenant_005: 545
- tenant_002: 526
- tenant_008: 504
- tenant_009: 184
