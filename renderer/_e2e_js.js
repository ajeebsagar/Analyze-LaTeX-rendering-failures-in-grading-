// End-to-end test for the browser-side JS pipeline (renderer.js).
// Verifies that the JS port produces the same auto-heal behavior for the
// same inputs that the Python pipeline handles.
const fs = require('fs');
const path = require('path');

// Build a minimal window shim and load renderer.js
const code = fs.readFileSync(path.join(__dirname, 'web', 'renderer.js'), 'utf8');
const sandbox = { window: {} };
const fn = new Function('window', code);
fn(sandbox.window);
const Renderer = sandbox.window.LatexRenderer;

const CASES = [
  // correct
  ['CORRECT: clean inline math',
   String.raw`If $\alpha$ and $\beta$ are zeroes of $x^2 - 1$.`,
   'authored_question',
   String.raw`If $\alpha$ and $\beta$ are zeroes of $x^2 - 1$.`,
   null],
  ['CORRECT: display math',
   String.raw`$$\int_0^1 x^2 dx = \frac{1}{3}$$`,
   'authored_question',
   String.raw`$$\int_0^1 x^2 dx = \frac{1}{3}$$`,
   null],
  // broken
  ['BROKEN: missing delim (rubric_criterion)',
   String.raw`\alpha + \beta = -\frac{1}{6}`,
   'rubric_criterion',
   String.raw`$\alpha + \beta = -\frac{1}{6}$`,
   'wrap_math_only'],
  ['BROKEN: orphan rac',
   String.raw`$\frac{1}{3} \times rac{2}{5}$`,
   'feedback',
   String.raw`$\frac{1}{3} \times \frac{2}{5}$`,
   'repair_orphan_rac'],
  ['BROKEN: glued alphaeta',
   String.raw`$\alpha + alphaeta = 5$`,
   'feedback',
   String.raw`$\alpha + \alpha\beta = 5$`,
   'repair_alphaeta'],
  ['BROKEN: HTML table -> fallback',
   '<table><tr><td>1</td></tr></table>',
   'authored_question',
   null,                                  // expected: fallback HTML
   null],
];

let passes = 0, fails = 0;
console.log('STATUS LABEL                                               PREP/OK');
console.log('-'.repeat(95));

for (const [label, text, fam, expectedPrep, mustHaveRepair] of CASES) {
  const r = Renderer.prepare(text, { sourceFamily: fam });
  let ok = true, reason = '';

  if (expectedPrep !== null && r.preparedText !== expectedPrep) {
    ok = false;
    reason = `prepared mismatch:\n      got: ${JSON.stringify(r.preparedText)}\n      exp: ${JSON.stringify(expectedPrep)}`;
  }
  if (mustHaveRepair && !r.repairs.includes(mustHaveRepair)) {
    ok = false;
    reason = `missing repair '${mustHaveRepair}'; got [${r.repairs.join(',')}]`;
  }
  if (label.includes('HTML table') && !r.html.includes('latex-fallback')) {
    ok = false;
    reason = `expected fallback span; got HTML: ${r.html.slice(0,80)}`;
  }

  if (ok) {
    console.log(`PASS   ${label.padEnd(50)} ok`);
    passes++;
  } else {
    console.log(`FAIL   ${label.padEnd(50)}`);
    console.log(`       ${reason}`);
    fails++;
  }
}
console.log();
console.log(`Total: ${passes}/${CASES.length} passed, ${fails} failed.`);
process.exit(fails === 0 ? 0 : 1);
