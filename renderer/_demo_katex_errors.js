// Demo: feed broken LaTeX directly to KaTeX (no preprocessing) and capture
// the error output. This is what KaTeX would print if the pipeline were
// disabled. Run with: node _demo_katex_errors.js
//
// Requires: npm install katex   (one-time)

let katex;
try { katex = require('katex'); }
catch (e) {
  console.log("npm package 'katex' is not installed.");
  console.log("Install once with:  npm install katex");
  console.log("Then re-run:        node _demo_katex_errors.js");
  process.exit(1);
}

const CASES = [
  ['Missing closing brace',          String.raw`\frac{1}{2`],
  ['Missing $ wrappers',             String.raw`\alpha + \beta = -\frac{1}{6}`],  // bare LaTeX
  ['Orphan eta (lost \\beta)',       String.raw`\alpha + eta + \alpha\beta`],
  ['Orphan rac (lost \\frac)',       String.raw`\frac{1}{3} \times rac{2}{5}`],
  ['Forbidden command',              String.raw`\input{secret.tex}`],
  ['Fill-in-the-blank subscript',    `Element is ______`],
];

console.log('='.repeat(80));
console.log('What KaTeX outputs when given BROKEN input directly (no pipeline)');
console.log('='.repeat(80));

for (const [label, input] of CASES) {
  console.log(`\n### ${label}`);
  console.log(`  INPUT: ${JSON.stringify(input)}`);

  // Mode 1: throwOnError=true — KaTeX throws
  try {
    katex.renderToString(input, { throwOnError: true, strict: 'ignore' });
    console.log(`  throwOnError:true   -> rendered OK (no error)`);
  } catch (err) {
    console.log(`  throwOnError:true   -> throws: ${err.name}`);
    console.log(`                         message: ${err.message}`);
    if (err.position != null) console.log(`                         position: ${err.position}`);
  }

  // Mode 2: throwOnError=false — KaTeX returns an error <span>
  const safeHtml = katex.renderToString(input, { throwOnError: false, strict: 'ignore' });
  // Extract the error message from the title attribute
  const m = safeHtml.match(/title="([^"]+)"/);
  const errorMsg = m ? m[1] : '(no error tag — rendered cleanly)';
  console.log(`  throwOnError:false  -> HTML contains: title="${errorMsg}"`);
  console.log(`                         visible text:  ${safeHtml.match(/>([^<]+)</)?.[1] ?? ''}`);
}
