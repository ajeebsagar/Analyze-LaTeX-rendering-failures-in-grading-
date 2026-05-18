# LaTeX Renderer Pipeline — End-to-End Implementation

Production-grade preprocessor for the Learnline LaTeX rendering problem. Implements the architecture from the analysis report:

```
Detect -> Classify -> Repair -> Validate -> Render -> Fallback
```

## What's in this folder

```
renderer/
  pipeline/
    segmenter.py    state-machine tokenizer ($..$, $$..$$, \(..\), \[..\])
    classifier.py   confidence-scored math-intent detector
    repair.py       Tier 1 (deterministic) + Tier 2 (heuristic, gated) repairs
    validator.py    pre-parse validation (depth, balance, forbidden commands)
    fallback.py     HTML-escape fallback (never throws)
    renderer.py     pipeline orchestrator + public API
  tests/
    test_pipeline.py  20+ test classes covering every failure bucket in the report
  web/
    playground.html  live browser playground (KaTeX from CDN)
    renderer.js      JS port of the pipeline so the playground works offline
  run_pipeline.py   CLI that processes the dataset and writes report + demo.html
```

## Quick start

### 1. Run the test suite

```powershell
# from the renderer/ directory
python -m unittest tests.test_pipeline -v
```

Expected: all tests pass.

### 2. Run the pipeline against a small slice of the dataset

```powershell
python run_pipeline.py --input ../golden_test_set.csv --outdir out/golden
python run_pipeline.py --input ../confirmed_broken.csv  --outdir out/broken --limit 1500
python run_pipeline.py --input ../tricky_examples.csv  --outdir out/tricky
```

Outputs in `out/<name>/`:
- `results.jsonl` — one record per input row with segment outcomes
- `report.json`   — aggregate stats (machine-readable)
- `report.md`     — human report
- `demo.html`     — open in a browser to see rendered output

### 3. Run against the full corpus

```powershell
python run_pipeline.py --input ../classified_candidates.jsonl --outdir out/full
```

This processes all 467,886 rows. Takes a few minutes.

### 4. Live playground

Open `web/playground.html` in a browser. Type or paste any text and watch the prepared output render with KaTeX in real time. Use the source-family dropdown to see how the family prior changes repair behavior.

## Public Python API

```python
from pipeline import prepare_text

result = prepare_text(
    "If $\\alpha$ and $\\beta$ are zeroes of $x^2 - 1$...",
    field_path="assignment_question.body.question_text",
)

result.prepared_text   # str ready for KaTeX auto-render
result.html            # HTML with <span class="latex-math"> placeholders
result.segments        # per-segment trace
result.repairs_applied # ['nfc_normalize', 'wrap_math_only', ...]
result.failure_reasons # validation rejections, if any
```

## Design contracts

1. **Storage is sacred.** Every repair is render-time only. The pipeline never writes to the DB.
2. **Pure functions.** Every stage is deterministic — same input, same output.
3. **Idempotent.** `prepare(prepare(x)) == prepare(x)` — verified by `test_pipeline.T_Idempotence`.
4. **Never throws.** The pipeline catches segmentation/validation failures and emits a fallback span; it does not propagate exceptions. The CLI also wraps `prepare_text` in try/except for defense in depth.
5. **No DB / network.** The pipeline has zero external dependencies — pure Python stdlib.

## How the pipeline maps to the analysis report

| Report stage | Code |
|---|---|
| Detect    | `segmenter.segment` |
| Classify  | `classifier.classify` + `family_of(field_path)` |
| Repair T1 | `repair.tier1_global`, `repair.tier1_math_segment`, `repair.tier1_prose_segment` |
| Repair T2 | `repair.tier2_wrap_math_only`, `repair.tier2_orphan_backslash` |
| Validate  | `validator.validate` |
| Render    | `renderer.prepare_text` -> placeholders; KaTeX (CDN or Node) fills them |
| Fallback  | `fallback.fallback_span` |

## Confidence thresholds (tunable)

```python
# pipeline/renderer.py
RENDER_CONFIDENCE_THRESHOLD = 0.55   # min score to render as math
REPAIR_CONFIDENCE_THRESHOLD = 0.70   # min score to apply Tier 2 repairs
```

Lower the render threshold to render more math (more false positives). Lower the repair threshold to apply more aggressive auto-fixes (more idempotence risk).

## Wiring to KaTeX

The pipeline output is intentionally agnostic about *who* invokes KaTeX:

- **Browser**: include the prepared HTML directly and let `auto-render.min.js` walk the DOM. See `web/playground.html` and the generated `demo.html`.
- **Server-side**: call `render_text(text, katex_render_fn=fn)` where `fn(latex, display) -> html` shells out to Node:

```python
import subprocess, json
def katex_node(latex, display):
    proc = subprocess.run(
        ["node", "-e",
         "const k=require('katex');process.stdout.write(k.renderToString(process.argv[1],{displayMode:JSON.parse(process.argv[2]),throwOnError:false,strict:'ignore'}));",
         latex, json.dumps(display)],
        capture_output=True, text=True, check=True)
    return proc.stdout
```

## Telemetry

`results.jsonl` from the CLI is the telemetry contract. Fields per row:

```json
{"dataset_row_id":"latex-0000028","category":"missing_math_delimiters",
 "family":"rubric_criterion","ui_surface":"rubric_or_steps",
 "had_math":true,"had_fallback":false,"pipeline_error":null,
 "segments":[{"kind":"math_inline","outcome":"math","score":0.87,
              "signals":{"known_commands":2,"sub":0,"super":1,...},
              "repairs":["strip_combining_diacritics"],
              "validation_reasons":[]}],
 "prepared_text":"$\\alpha + \\beta = -\\frac{1}{6}$..."}
```

Hook this into Prometheus / Grafana by emitting one counter per `(family, outcome, repair)` tuple.

## CI gate

In CI, run the test suite + a regression-check against `confirmed_broken.csv`:

```bash
python -m unittest tests.test_pipeline -v
python run_pipeline.py --input ../confirmed_broken.csv --outdir out/regression
# Fail the build if fallback_rate regresses beyond the agreed budget.
python -c "import json; r=json.load(open('out/regression/report.json')); assert r['fallback_rate'] < 0.05, r['fallback_rate']"
```
