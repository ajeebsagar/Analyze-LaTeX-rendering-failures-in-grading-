"""Convert END_TO_END_WORKFLOW.md to PDF using Python markdown + Chrome headless."""
import os
import shutil
import subprocess
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import markdown

ROOT = os.path.dirname(os.path.abspath(__file__))
MD_FILE = os.path.join(ROOT, "docs", "END_TO_END_WORKFLOW.md")
HTML_FILE = os.path.join(ROOT, "docs", "END_TO_END_WORKFLOW.html")
PDF_FILE = os.path.join(ROOT, "docs", "END_TO_END_WORKFLOW.pdf")

# ---- Step 1: markdown → HTML ----
print(f"Loading markdown: {MD_FILE}")
md_text = open(MD_FILE, encoding="utf-8").read()

md = markdown.Markdown(extensions=[
    "tables", "fenced_code", "toc", "sane_lists", "codehilite",
])
body_html = md.convert(md_text)

CSS = """
@page { size: A4; margin: 14mm 16mm 16mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
  color: #1c2025; line-height: 1.5; font-size: 11pt;
  max-width: 100%; padding: 0; margin: 0;
}
h1 { font-size: 22pt; color: #102040; border-bottom: 2px solid #1764d9;
     padding-bottom: 6px; margin-top: 18pt; page-break-after: avoid; }
h2 { font-size: 16pt; color: #1764d9; margin-top: 14pt; page-break-after: avoid; }
h3 { font-size: 13pt; color: #224066; margin-top: 10pt; page-break-after: avoid; }
h4 { font-size: 12pt; color: #2c3e50; margin-top: 8pt; }
p  { margin: 6pt 0; }
hr { border: none; border-top: 1px solid #c4cee0; margin: 14pt 0; }
ul, ol { margin: 4pt 0 4pt 20pt; padding: 0; }
li { margin: 2pt 0; }
code {
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  background: #eef1f6; padding: 1px 4px; border-radius: 3px;
  font-size: 9.5pt; color: #1f2d3d;
}
pre {
  background: #1e293b; color: #e2e8f0;
  padding: 10px 12px; border-radius: 6px; overflow-x: auto;
  font-family: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  font-size: 8.5pt; line-height: 1.4;
  page-break-inside: avoid; white-space: pre-wrap; word-break: break-word;
}
pre code { background: none; color: inherit; padding: 0; }
table {
  border-collapse: collapse; margin: 8pt 0; width: 100%;
  font-size: 9.5pt; page-break-inside: avoid;
}
th, td {
  border: 1px solid #cbd5e1; padding: 4px 8px; text-align: left;
  vertical-align: top; word-break: break-word;
}
th { background: #eef1f6; color: #1c2025; font-weight: 600; }
tr:nth-child(even) td { background: #fafbfd; }
a { color: #1764d9; text-decoration: none; }
strong { color: #102040; }
blockquote { border-left: 3px solid #94a3c4; padding: 4px 12px; margin: 8pt 0;
             background: #f4f6fa; color: #475569; }

/* Print niceties */
@media print {
  body { print-color-adjust: exact; -webkit-print-color-adjust: exact; }
}

/* Footer with page numbers */
.footer-line { text-align: center; color: #888; font-size: 9pt; margin-top: 12pt; }
"""

full_html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>LaTeX Renderer Pipeline — End-to-End Workflow</title>
<style>{CSS}</style>
</head>
<body>
{body_html}
<hr>
<div class="footer-line">LaTeX Renderer Pipeline — End-to-End Implementation Reference</div>
</body>
</html>
"""

with open(HTML_FILE, "w", encoding="utf-8") as f:
    f.write(full_html)
print(f"Wrote intermediate HTML: {HTML_FILE} ({os.path.getsize(HTML_FILE)/1024:.1f} KB)")

# ---- Step 2: HTML → PDF using Chrome headless ----
chrome_candidates = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    shutil.which("chrome"),
    shutil.which("google-chrome"),
    shutil.which("chromium"),
]
chrome = next((c for c in chrome_candidates if c and os.path.exists(c)), None)

if not chrome:
    print("\nNo Chrome / Chromium found. The HTML has been generated.")
    print(f"  Open in browser: {HTML_FILE}")
    print(f"  Then press Ctrl+P → Save as PDF.")
    sys.exit(0)

print(f"\nUsing Chrome: {chrome}")
file_url = "file:///" + HTML_FILE.replace("\\", "/")
cmd = [
    chrome,
    "--headless=new",
    "--disable-gpu",
    "--no-sandbox",
    "--no-pdf-header-footer",
    f"--print-to-pdf={PDF_FILE}",
    "--print-to-pdf-no-header",
    "--virtual-time-budget=2000",
    file_url,
]
print(f"Running: chrome --headless --print-to-pdf …")
try:
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if os.path.exists(PDF_FILE) and os.path.getsize(PDF_FILE) > 1000:
        sz = os.path.getsize(PDF_FILE) / 1024
        print(f"\nWrote PDF: {PDF_FILE} ({sz:.1f} KB)")
        print(f"  Done. Open with your PDF viewer.")
    else:
        print(f"\nChrome ran but did not produce a usable PDF.")
        if result.stderr:
            print(f"  stderr (head): {result.stderr[:400]}")
        print(f"  Fallback — open the HTML and Print → Save as PDF:")
        print(f"    {HTML_FILE}")
except subprocess.TimeoutExpired:
    print("Chrome timed out. Open the HTML manually and Print → Save as PDF.")
    print(f"  {HTML_FILE}")
