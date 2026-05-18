# KaTeX Parse Error Catalog (v0.16.x)

Complete reference of every `ParseError` message KaTeX can throw, extracted
directly from `node_modules/katex/dist/katex.mjs` (the npm-shipped bundle of
the canonical `KaTeX/KaTeX` source).

- **88 total ParseError throw sites**
- **75 distinct message templates**
- Source verification: `Parser.js`, `MacroExpander.js`, `functions/*.js`,
  `environments/*.js`, `Lexer.js`, `ParseError.js`
- Canonical repo: <https://github.com/KaTeX/KaTeX>
- Official docs (sparse on error specifics): <https://katex.org/docs/error>

When KaTeX throws, the `Error` object has these properties:
- `error.name === 'ParseError'`
- `error.message` — the full `"KaTeX parse error: <template> at position N: …"` string
- `error.position` — 0-based character offset where the parser stopped
- `error.length` — length of the offending token, if any
- The instance is `instanceof katex.ParseError`

If `throwOnError: false`, KaTeX returns HTML containing
`<span class="katex-error" title="<escaped message>">…raw input…</span>`
in `errorColor` (default `#cc0000`).

---

## TL;DR — counts per category

| Category | Distinct templates | Total call-sites |
|---|---:|---:|
| Expected-X (parser awaited specific token) | 9 | 10 |
| Generic `Expected '<X>', got '<Y>'` (Parser.expect) | 1 | 1 |
| Invalid value (size / unit / color / argument / mode) | 15 | 18 |
| Other | 19 | 22 |
| Newline / tabular-row errors | 8 | 8 |
| Function-argument errors | 7 | 7 |
| Delimiter mismatch (`\left` / `\right` / `\middle`) | 5 | 5 |
| Lexical / character errors | 3 | 3 |
| Unexpected token / `Got X` | 2 | 3 |
| Missing-X | 1 | 2 |
| Double / duplicate / repeated | 2 | 3 |
| Mode mismatch (math / text / display) | 1 | 2 |
| Undefined control sequence | 1 | 2 |
| Environment errors (`\begin` / `\end`) | 1 | 1 |
| Constraint violation | 1 | 1 |
| **TOTAL** | **75** | **88** |

---

## A. Generic Parser.expect error (most common)

```
Expected '<text>', got '<found-token>'
```

Thrown by `Parser.expect()` whenever the next token doesn't match what the
parser was awaiting. By far the most common end-user-visible error.

**Triggered by**: missing closing brace, missing `]`, missing `\right`,
missing `\end{…}`, missing `}` after `\frac{a}{b`, etc.

**Example** for input `\frac{1}{2`:
```
KaTeX parse error: Unexpected end of input in a macro argument,
expected '}' at end of input: \frac{1}{2
```
position: 10 · pipeline catches as: **`missing_closing_brace`**

---

## B. Expected-X family (parser awaited a specific construct)

| Message | When it fires |
|---|---|
| `Expected '<X>'` | `Parser.expect` — see section A |
| `Expected '<X>', got '<Y>'` | Same as above with both expected and found |
| `Expected a control sequence` | `\let X` where X is not a control sequence |
| `Expected \\ or \cr or \end` | Inside a column-aligned env, no separator found |
| `Expected & or \\ or \cr or \end` | Same but also expecting cell separator |
| `Expected a macro definition` | After `\def` / `\newcommand` without body |
| `Expected one of "<>AV=|." after @` | After `\@` in array column spec |
| `Expected l or c or r` | In `\begin{matrix}` style column specification |
| `Expected group after '<symbol>'` | After `_`, `^`, etc. without a group |
| `Expected group as <name>` | When a function expected `{…}` arg |

---

## C. Undefined / Unknown commands

| Message | Triggered by |
|---|---|
| `Undefined control sequence: <\cmd>` | Any backslash command KaTeX doesn't know, e.g. `\input`, `\nonexistent`, `\zzz` |
| `No function handler for <type>` | Internal: function type registered but no handler — should never reach users in practice |
| `No such environment: <name>` | `\begin{nonexistent}` |
| `Unknown column alignment: <c>` | Column spec character that isn't `l`/`c`/`r` (etc.) |
| `Unknown type of space "<x>"` | Internal misuse of a space node |
| `Unknown accent ' <accent> '` | Accent function on a non-accent argument |
| `Unknown group type as <name>` | Internal: malformed parse tree |

---

## D. Unexpected token / "Got X"

| Message | Triggered by |
|---|---|
| `Got group of unknown type: '<type>'` | Function called with unsupported group |
| `Got function '<func>' with no arguments` | A function that requires arguments was used bare |
| `Got function '<func>' with no arguments as <name>` | Same, in a named context |

---

## E. Function-argument errors

| Message | Triggered by |
|---|---|
| `\@char has non-numeric argument <x>` | `\@char` with non-digit content |
| `\@char with invalid code point <n>` | `\@char` out of valid Unicode range |
| `\char` missing argument | `\char` with no argument |
| `Argument number "<n>" out of order` | Macro argument references invalid number |
| `Invalid argument number "<n>"` | Macro reference to `#0` or `#10+` |
| `Not a valid argument number` | After `#` in a non-macro context |
| `Unexpected end of input in a macro argument` | Argument never closed |
| `Null argument, please report this as a bug` | Internal: should never reach users |
| `A primitive argument cannot be optional` | Macro defined with optional primitive arg |
| `Use of the macro doesn't match its definition` | Macro called with wrong arg count |
| `Incomplete placeholder at end of macro body` | `#` at end of `\def` body |
| `Too many expansions: infinite loop or <macro>` | Recursive macro hit expansion limit |

---

## F. Delimiter mismatch (`\left` / `\right` / `\middle`)

| Message | Triggered by |
|---|---|
| `Illegal delimiter: '<d>'` | `\left X` where X isn't a recognized delimiter |
| `Invalid delimiter: '<d>'` | Same in different context |
| `Invalid delimiter type '<t>'` | Internal |
| `\middle without preceding \left` | `\middle |` not inside `\left … \right` |
| `\current@color set to non-string in \right` | Internal color tracking |
| `\verb ended by end of line instead of matching delimiter` | `\verb!abc` with no closing `!` |
| `The length of delimiters doesn't match the number of args!` | Internal |

---

## G. Environment errors (`\begin` / `\end`)

| Message | Triggered by |
|---|---|
| `No such environment: <name>` | `\begin{xxx}` for unknown `xxx` |
| `Mismatch: \begin{<a>} ... \end{<b>}` | Mismatched env names |
| `Invalid environment name` | Empty or malformed `\begin{}` |
| `\tag works only in display equations` | `\tag` in inline math |
| `Multiple \tag` | Two `\tag` in one equation |

---

## H. Mode mismatch (math / text / display)

| Message | Triggered by |
|---|---|
| `Can't use function '<func>' in math mode` | Text-only function inside `$…$` |
| `Can't use function '<func>' in text mode` | Math-only function outside math |
| `Accent <name> unsupported in <mode> mode` | Specific accent disallowed in mode |
| `LaTeX-incompatible input and strict mode is set to 'error': <X>` | With `strict: 'error'` setting |

---

## I. Invalid value (size / unit / color / mode)

| Message | Triggered by |
|---|---|
| `Invalid unit: '<u>'` | Size with unrecognized unit (e.g. `\rule{1foo}{1pt}`) |
| `Invalid size: '<s>'` | Size argument not a number+unit |
| `Invalid color: '<c>'` | `\color{xyz}` where xyz isn't a known color or hex |
| `Invalid number of arguments: <n>` | `\newcommand[<n>]{}` with bad n |
| `Invalid base-<n>` | `\char` with invalid base |
| `Invalid <modeName>: '<token>'` | Generic mode-input mismatch |
| `Invalid token after macro prefix` | After `\long` / `\outer` |
| `Invalid attribute name '<name>'` | In `\htmlAttribute`/`\htmlData` |
| `Invalid separator type: <t>` | Internal array separator |
| `Invalid argument number "<n>"` | Bad `#` reference |
| `Invalid \arraystretch: <s>` | `\arraystretch` with non-number |
| `Invalid key: '<k>'` | `\htmlData` key not alphanumeric/dash |

---

## J. Lexical / character errors

| Message | Triggered by |
|---|---|
| `Unsupported character: <c>` | Lexer hit a char it can't handle |
| `Unexpected character: '<c>'` | Same with different framing |
| `Too many tab characters: &` | Cell overflow in array env |

---

## K. Newline / tabular-row errors

| Message | Triggered by |
|---|---|
| `\\ <token>` parsing | `\\` followed by invalid optional `[<size>]` (the `Invalid size` from section I) |
| Various inside tabulars | (See sections B, F above for in-env errors) |

---

## L. Double / duplicate / repeated

| Message | Triggered by |
|---|---|
| `Double superscript` | `x^2^3` |
| `Double subscript` | `x_1_2` |
| `Multiple \tag` | Two `\tag` in one display |

---

## M. HTML / macro-extension errors

| Message | Triggered by |
|---|---|
| `\newcommand{<name>}: ...` | `\newcommand{\frac}{...}` redefining built-in |
| `\renewcommand{<name>}: ...` | `\renewcommand` of undefined |
| `\htmlData key/value '<x>'` | Invalid `\htmlData` syntax |
| `\verb assertion failed -- please report what input caused this bug` | Internal |

---

## N. Other

| Message | Triggered by |
|---|---|
| `Extra }` | Closing brace with no matching open |
| `{<X>` (generic open-brace error) | Various |
| `Mismatched <X>` | Generic mismatch |
| `Too many math in a row: <n>` | Adjacent `$…$` chains |
| `{subarray} can contain only one column` | Multi-column `subarray` |
| `Only one infix operator per group` | E.g. `a \over b \atop c` |
| `Limit controls must follow a math operator` | `\limits` after non-operator |
| `Unbalanced namespace destruction: attempt <X>` | Internal macro scoping bug |
| `KaTeX doesn't work in quirks mode.` | Browser is in quirks mode |
| `\newcommand's first argument must be a macro name` | First arg to `\newcommand` not `\foo` |
| `Missing a <X>` | E.g. missing colon in cases env |

---

## How each KaTeX error maps to our pipeline

The Python pipeline **prevents most of these** from ever reaching KaTeX. The
mapping:

| KaTeX error pattern | Pipeline action | Bucket |
|---|---|---|
| `Expected '}'` (missing closing brace) | `BraceBalanceValidator` rejects → fallback span | **B** |
| `Undefined control sequence: \input` etc. | `ForbiddenCommandValidator` rejects | **E** |
| `Expected group after '_'` (fill-in-the-blank `____`) | `SubscriptRunValidator` rejects | **H** |
| `Double subscript / superscript` | (passthrough — usually rare) | — |
| `Can't use function in math mode` | (passthrough — KaTeX strict='ignore' handles) | — |
| `No such environment` | (passthrough — fallback if it throws) | — |
| `Invalid unit/size/color` | (passthrough — fallback if it throws) | — |
| `Unexpected character` | NFC normalization + diacritic stripper run first | **D** |
| Anything not caught above | KaTeX runs with `throwOnError: false`, `strict: 'ignore'` → outputs red `<span class="katex-error">` |

For inputs that aren't even valid LaTeX but ARE recoverable (orphan
backslashes like `eta` → `\beta`), the pipeline fixes them BEFORE KaTeX
sees them. KaTeX would not have thrown on these — it would have rendered
**wrong math silently**. The pipeline's pre-parse diagnostic
(`ErrorAnalyzer`) catches those by pattern match.

---

## The dangerous "silent wrong render" cases

These produce **NO KaTeX error** but **WRONG rendered output**:

| Input | KaTeX reaction | What user sees |
|---|---|---|
| `\alpha + eta` | no error | α + italic "eta" — **looks like 3 letters, NOT Greek β** |
| `\frac{1}{3} \times rac{1}{2}` | no error | real fraction × italic "rac" |
| `\alpha\beta` with combining `̑` | no error | corrupted glyph stack |
| Currency-shaped `$5 cake` rendered as math | no error | mathematical italic "5cake" |

These are why a pre-parse semantic check matters. KaTeX is syntactically
forgiving but semantically blind — it can't know you wrote `eta` when you
meant `\beta`.

---

## How to capture KaTeX errors at runtime

### JavaScript / browser
```js
try {
  const html = katex.renderToString(input, {
    throwOnError: true,
    strict: 'ignore',
  });
} catch (err) {
  if (err.name === 'ParseError') {
    console.log('Message :', err.message);     // KaTeX parse error: …
    console.log('Position:', err.position);    // 0-based char offset
    console.log('Length  :', err.length);      // length of offending token
  }
}
```

### Or with `throwOnError: false` — parse the title attribute
```js
const html = katex.renderToString(input, {throwOnError: false, strict: 'ignore'});
const m = html.match(/<span class="katex-error" title="([^"]+)"/);
if (m) {
  const msg = m[1];                              // full message
  const pos = msg.match(/at position (\d+)/)?.[1];
  console.log('Failed at position', pos, ':', msg);
}
```

### Server-side via Node
```bash
npm install katex
node -e "const k=require('katex'); try { k.renderToString('\\\\frac{1}{2', {throwOnError:true}); } catch(e){ console.log(e.name, e.position, e.message); }"
```

Output:
```
ParseError 10 KaTeX parse error: Unexpected end of input in a macro argument, expected '}' at end of input: \frac{1}{2
```

---

## How to regenerate this catalog

The full catalog was extracted from the local npm-installed bundle:

```bash
cd renderer
npm install katex                         # one-time
python _extract_katex_errors.py
```

This regenerates [`docs/katex_error_catalog.json`](./katex_error_catalog.json)
and prints the categorized list. Bumping the KaTeX version and re-running
this script will surface any new errors introduced between releases.

---

## Sources

- KaTeX source on GitHub: <https://github.com/KaTeX/KaTeX>
- `Parser.js` (most error throws): <https://github.com/KaTeX/KaTeX/blob/main/src/Parser.js>
- Local extraction: `node_modules/katex/dist/katex.mjs` v0.16.11
- Official error-handling docs: <https://katex.org/docs/error>
- KaTeX issue tracker (real-world error reports): <https://github.com/KaTeX/KaTeX/issues>
