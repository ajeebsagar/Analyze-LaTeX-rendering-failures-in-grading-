// Verify the JS browser pipeline heals the user's exact input.
const fs = require('fs');
const path = require('path');
const code = fs.readFileSync(path.join(__dirname, 'web', 'renderer.js'), 'utf8');
const sandbox = { window: {} };
new Function('window', code)(sandbox.window);
const Renderer = sandbox.window.LatexRenderer;

const cases = [
  [String.raw`\alpha + eta = -\frac{1}{6}$`,            'rubric_criterion', String.raw`$\alpha + \beta = -\frac{1}{6}$`],
  [String.raw`$\alpha + \beta = -\frac{1}{6}`,          'rubric_criterion', String.raw`$\alpha + \beta = -\frac{1}{6}$`],
  ['Cost: $5 only.',                                    'feedback',         'Cost: $5 only.'],
  [String.raw`x = rac{1}{2} + \alpha`,                  'rubric_criterion', String.raw`$x = \frac{1}{2} + \alpha$`],
];
let pass = 0, fail = 0;
console.log('STATUS  INPUT                                              -> OUTPUT');
console.log('-'.repeat(95));
for (const [input, fam, expected] of cases) {
  const r = Renderer.prepare(input, { sourceFamily: fam });
  const ok = r.preparedText === expected;
  (ok ? pass++ : fail++);
  console.log(`${ok ? 'PASS' : 'FAIL'}    ${JSON.stringify(input).padEnd(50)} -> ${JSON.stringify(r.preparedText)}`);
  if (!ok) console.log(`        expected: ${JSON.stringify(expected)}`);
  console.log(`        repairs: [${r.repairs.join(',')}]`);
}
console.log(`\n${pass}/${cases.length} passed.`);
process.exit(fail === 0 ? 0 : 1);
