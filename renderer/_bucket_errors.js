// For each bucket (A-L, Z), feed a representative broken input directly to
// KaTeX and capture the exact ParseError. Run: `node _bucket_errors.js`
// Requires katex installed: `npm install katex`

const katex = require('katex');

const CASES = [
  // bucket, label, input (raw — no pipeline preprocessing)
  ['A', 'missing_delimiters',
   String.raw`\alpha + \beta = -\frac{1}{6}`,
   'Bare LaTeX without $..$ delimiters. In renderToString it parses fine ' +
   '(renderToString assumes math mode), but in browser auto-render it would ' +
   "never enter math mode → text shows raw '\\alpha + \\beta'."],

  ['B-1', 'broken_braces — missing closing }',
   String.raw`\frac{1}{2`,
   'Unclosed group brace.'],

  ['B-2', 'broken_braces — extra closing }',
   String.raw`\frac{1}{2}}`,
   'Surplus closing brace at top level.'],

  ['C-1', 'unbalanced_dollar — empty math segment',
   String.raw`text $$ more`,
   'Two adjacent dollars produce an empty display math segment.'],

  ['C-2', 'unbalanced_dollar — leading orphan in renderToString',
   String.raw`$\alpha + \beta`,
   'In auto-render mode the unmatched $ never enters math; renderToString ' +
   'treats input as math so this is its raw-parse view.'],

  ['D-1', 'ocr_corruption — orphan eta (no error fires)',
   String.raw`\alpha + eta + \alpha\beta`,
   'KaTeX renders this SILENTLY WRONG: "eta" becomes 3 italic letters, not β.'],

  ['D-2', 'ocr_corruption — orphan rac (no error fires)',
   String.raw`\frac{1}{3} \times rac{2}{5}`,
   'Same silent-wrong behavior: "rac" renders as 3 italic letters.'],

  ['D-3', 'ocr_corruption — combining diacritic (no error)',
   '\\alpha + \\beta + ̑\\alpha',
   'KaTeX renders the diacritic as a stacking glyph — visually corrupt.'],

  ['E', 'invalid_command_name — security-blocked',
   String.raw`\input{/etc/passwd}`,
   'Forbidden command. KaTeX reports an undefined control sequence.'],

  ['F', 'unsupported_environment — \\begin{xxx}',
   String.raw`\begin{nonexistent} 1 \end{nonexistent}`,
   'Unknown environment name.'],

  ['G', 'mixed_prose_math (clean, no error)',
   String.raw`If $\alpha$ and $\beta$ are zeroes`,
   'Mixed prose + math is a NORMAL valid pattern; included here for control.'],

  ['H-1', 'false_positive — fill-in-the-blank',
   String.raw`Element is ______`,
   'Run of underscores — KaTeX builds an infinitely nested subscript chain.'],

  ['H-2', 'false_positive — \\text{______}',
   String.raw`x = \text{_______}`,
   'Fill-in-the-blank inside \\text{} — same KaTeX error from `_`.'],

  ['I', 'code_snippet (n/a — would be markdown path)',
   '```python\nprint(1)\n```',
   'Code fences should be intercepted before KaTeX. If KaTeX sees them...'],

  ['J', 'currency_text — orphan $ in prose',
   `The book costs $5 and the pen costs $3.`,
   'Two $ characters in prose — KaTeX would see the text between them as math.'],

  ['K', 'nested_parser_corruption — \\text containing math',
   String.raw`\frac{1}{\text{\sqrt{3}}}`,
   'Nested math inside \\text — depends on strict mode.'],

  ['L-1', 'multiline_ai_solution — literal \\n',
   String.raw`Step 1: do thing.\nStep 2: do other.`,
   'Literal "\\n" sequence — KaTeX tries to expand \\n as a control word.'],

  ['L-2', 'multiline_ai_solution — \\n inside math',
   String.raw`$\alpha\nbeta$`,
   'Same in math context.'],

  ['Z', 'clean (control — should render with no error)',
   String.raw`\frac{1}{2} + \alpha`,
   'Should render with no error or warning.'],
];

function summarize(err) {
  if (!err) return null;
  return {
    name: err.name,
    message: err.message,
    position: err.position ?? null,
    length: err.length ?? null,
  };
}

console.log('='.repeat(96));
console.log('Exact KaTeX errors for each bucket (raw inputs, throwOnError:true, strict:\'error\')');
console.log('='.repeat(96));

for (const [bucket, label, input, note] of CASES) {
  console.log(`\n─────────────────────────────────────────────────────────────────────────`);
  console.log(`  BUCKET ${bucket}  ·  ${label}`);
  console.log(`─────────────────────────────────────────────────────────────────────────`);
  console.log(`  INPUT  : ${JSON.stringify(input)}`);
  console.log(`  NOTE   : ${note}`);

  // Mode 1 — throwOnError:true, strict:'ignore' (our prod config baseline)
  try {
    katex.renderToString(input, { throwOnError: true, strict: 'ignore' });
    console.log(`  throwOnError:true, strict:'ignore'`);
    console.log(`    -> SILENT (no error; KaTeX rendered something — possibly WRONG output)`);
  } catch (e) {
    const s = summarize(e);
    console.log(`  throwOnError:true, strict:'ignore'`);
    console.log(`    -> ${s.name}: ${s.message}`);
    if (s.position != null) console.log(`       position=${s.position}  length=${s.length}`);
  }

  // Mode 2 — strict:'error' (catches everything stricter, useful for diagnostic)
  try {
    katex.renderToString(input, { throwOnError: true, strict: 'error' });
    console.log(`  throwOnError:true, strict:'error'`);
    console.log(`    -> SILENT (no error)`);
  } catch (e) {
    const s = summarize(e);
    console.log(`  throwOnError:true, strict:'error'`);
    console.log(`    -> ${s.name}: ${s.message}`);
    if (s.position != null) console.log(`       position=${s.position}  length=${s.length}`);
  }

  // Mode 3 — throwOnError:false (production mode) — produces error span HTML
  const html = katex.renderToString(input, { throwOnError: false, strict: 'ignore' });
  const m = html.match(/<span class="katex-error" title="([^"]+)"/);
  if (m) {
    // Unescape the &#x27; etc.
    const msg = m[1]
      .replace(/&#x27;/g, "'").replace(/&quot;/g, '"')
      .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
    console.log(`  throwOnError:false (PRODUCTION mode)`);
    console.log(`    -> HTML embeds: title="${msg}"`);
  } else {
    console.log(`  throwOnError:false (PRODUCTION mode)`);
    console.log(`    -> Rendered cleanly (no error span emitted)`);
  }
}
