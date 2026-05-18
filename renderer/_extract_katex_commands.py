"""Extract every command name KaTeX recognizes from the installed katex.mjs,
then diff against our MATH_COMMANDS set to find what's missing."""
import os, re, sys
from collections import Counter

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

KATEX = os.path.join(os.path.dirname(__file__), "node_modules", "katex", "dist", "katex.mjs")
src = open(KATEX, encoding="utf-8").read()
print(f"Loaded {KATEX} ({len(src):,} bytes)")

# KaTeX defines commands several ways. We extract from all of them.
# 1. defineSymbol(mode, font, type, replace, name)   — single-name symbol
# 2. defineFunction({names: ["\\foo", "\\bar"], ...}) — function with one or more names
# 3. defineMacro("\\name", expander)                  — macro alias
# 4. names: ["\\foo", ...] literal arrays              — function name lists

names = set()

# Pattern 1: defineSymbol calls — 5 args, last is the printable name; we want
# entries where the name starts with \ (control sequences).
for m in re.finditer(r'defineSymbol\([^,]+,[^,]+,[^,]+,[^,]+,\s*"\\\\([a-zA-Z]+)"', src):
    names.add(m.group(1))

# Pattern 2: defineFunction({names:[...] or name:"..."}) — capture every
# control-sequence name inside the names array.
for m in re.finditer(r'names:\s*\[([^\]]*)\]', src):
    body = m.group(1)
    for nm in re.finditer(r'"\\\\([a-zA-Z@]+)"', body):
        names.add(nm.group(1))

# Pattern 3: single-name defineFunction
for m in re.finditer(r'name:\s*"\\\\([a-zA-Z@]+)"', src):
    names.add(m.group(1))

# Pattern 4: defineMacro("\\name", ...)
for m in re.finditer(r'defineMacro\("\\\\([a-zA-Z@]+)"', src):
    names.add(m.group(1))

# Pattern 5: macros[r"\name"] = ... (assignment form)
for m in re.finditer(r'macros\["\\\\([a-zA-Z@]+)"\]', src):
    names.add(m.group(1))

# Filter: drop any names starting with @ (internal) — keep them but mark
internal = {n for n in names if n.startswith("@")}
public = names - internal

print(f"\nTotal control-sequence names found: {len(names):,}")
print(f"  Public (no @ prefix): {len(public):,}")
print(f"  Internal (@-prefixed): {len(internal)}")

# Now compare against our current MATH_COMMANDS set
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
from latex_pipeline.classification.signals import MATH_COMMANDS

current = set(MATH_COMMANDS)
missing = public - current
extra = current - public

print(f"\nCurrent MATH_COMMANDS size:        {len(current):,}")
print(f"  - Present and in KaTeX:          {len(current & public):,}")
print(f"  - In our set but NOT in KaTeX:   {len(extra):,}")
print(f"  - In KaTeX but NOT in our set:   {len(missing):,}   <-- coverage gap")

# Group missing commands into useful categories
def categorize(name):
    n = name.lower()
    if n in {"gcd","lcm","det","arg","deg","ker","exp","hom","dim","min","max","sup","inf","liminf","limsup","mod","bmod","pmod","pod","operatorname","operatornamewithlimits"}:
        return "1. Operators (gcd, det, exp, arg, ker, ...)"
    if n in {"zeta","aleph","beth","gimel","daleth","ell","hbar","wp","Re","Im","imath","jmath","forall","exists","nexists","emptyset","varnothing","top","bot","partial","infty","nabla"}:
        return "2. Letter-like symbols (zeta, aleph, ell, hbar, ...)"
    if re.match(r"^(var|operator|math)", n):
        return "3. Math-mode style commands (var*, math*, operator*)"
    if n in {"binom","tbinom","dbinom","over","atop","choose","frac","tfrac","dfrac","cfrac","sqrt","root","sum","prod","int","oint","iint","iiint","bigcup","bigcap","bigvee","bigwedge","bigsqcup","bigotimes","bigodot","bigoplus","biguplus","coprod"}:
        return "4. Big operators / fractions / roots"
    if n in {"begin","end","matrix","pmatrix","bmatrix","Bmatrix","vmatrix","Vmatrix","smallmatrix","cases","array","aligned","gathered","alignedat","split","equation","eqnarray","subarray"}:
        return "5. Environments"
    if n in {"left","right","middle","big","Big","bigg","Bigg","bigl","Bigl","biggl","Biggl","bigr","Bigr","biggr","Biggr","bigm","Bigm","biggm","Biggm"}:
        return "6. Delimiter sizing"
    if n in {"hat","tilde","bar","vec","dot","ddot","check","breve","grave","acute","mathring","widehat","widetilde","overline","underline","overrightarrow","overleftarrow","overbrace","underbrace","overparen","underparen","stackrel","overset","underset"}:
        return "7. Accents / decorations"
    # Greek-like
    if n in {"alpha","beta","gamma","delta","epsilon","varepsilon","zeta","eta","theta","vartheta","iota","kappa","varkappa","lambda","mu","nu","xi","omicron","pi","varpi","rho","varrho","sigma","varsigma","tau","upsilon","phi","varphi","chi","psi","omega","Gamma","Delta","Theta","Lambda","Xi","Pi","Sigma","Upsilon","Phi","Psi","Omega"}:
        return "8. Greek letters"
    if n in {"text","textit","textbf","textsf","texttt","textrm","textmd","textnormal","textup","emph","textcolor"}:
        return "9. Text-mode commands"
    if "arrow" in n or "rightarrow" in n or "leftarrow" in n or "mapsto" in n or "hookrightarrow" in n or "twoheadrightarrow" in n or "rightleftharpoons" in n or "leftrightharpoons" in n:
        return "A. Arrows"
    if "color" in n or "rgb" in n:
        return "B. Color commands"
    if n in {"mathbb","mathbf","mathcal","mathfrak","mathit","mathrm","mathscr","mathsf","mathtt","mathnormal","Bbb","cal","frak","bm","boldsymbol","mit"}:
        return "C. Math fonts"
    if n in {"limits","nolimits","substack","mathop","mathbin","mathrel","mathopen","mathclose","mathpunct","mathord","mathinner"}:
        return "D. Math spacing/role classifiers"
    if n in {"href","url","textbf","includegraphics","verb","kern","hskip","vskip","mskip","quad","qquad","hspace","vspace","phantom","hphantom","vphantom"}:
        return "E. Layout / external"
    return "Z. Other (chemical, color, layout, misc)"

cats = {}
for m in sorted(missing):
    cats.setdefault(categorize(m), []).append(m)

print("\n" + "=" * 88)
print(f"MISSING COMMANDS — what we should add (or not) to MATH_COMMANDS")
print("=" * 88)
for cat in sorted(cats):
    items = cats[cat]
    print(f"\n## {cat}   ({len(items)} missing)")
    for chunk_start in range(0, len(items), 8):
        chunk = items[chunk_start:chunk_start+8]
        print("  " + "  ".join(f"\\{n}" for n in chunk))

# Write the full list to a file
out = os.path.join(os.path.dirname(__file__), "docs", "katex_commands_missing.txt")
os.makedirs(os.path.dirname(out), exist_ok=True)
with open(out, "w", encoding="utf-8") as f:
    f.write("# Commands present in KaTeX but absent from our MATH_COMMANDS set\n")
    f.write(f"# Total missing: {len(missing)}\n")
    f.write(f"# Source: {KATEX}\n\n")
    for cat in sorted(cats):
        f.write(f"\n## {cat}   ({len(cats[cat])})\n")
        for m in cats[cat]:
            f.write(f"\\{m}\n")
print(f"\nFull list written to {out}")
