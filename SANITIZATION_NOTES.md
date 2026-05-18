# Sanitization Notes

- Tenant names are mapped to `tenant_001`, `tenant_002`, etc.
- Assignment, student assignment, submission, graded item, and question IDs are mapped to neutral stable labels.
- Assignment titles and sections are mapped to neutral labels.
- Known client names inside `raw_text` are replaced with `<client>`.
- Emails, phone numbers, URLs, and S3 paths are replaced with placeholders.
- Educational text, math expressions, rubric wording, feedback wording, annotations, categories, and field paths are preserved.
