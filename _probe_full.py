import json, re
from collections import Counter, defaultdict

BROKEN_CATS = {'missing_math_delimiters','likely_math_missing_delimiters',
               'unbalanced_dollar','bad_brace_balance','katex_parse_error',
               'latex_parse_error','bad_super_or_subscript',
               'html_or_markdown_mixed_text','unsupported_latex_command',
               'display_or_mode_conflict'}
TRICKY = {'tricky_false_positive'}

probes = {
    'has_frac':            re.compile(r'\\frac\b'),
    'has_greek':           re.compile(r'\\(alpha|beta|gamma|theta|pi|sigma|lambda|mu|nu|rho|delta|phi|psi|omega|tau|epsilon|chi)\b'),
    'has_sqrt':            re.compile(r'\\sqrt\b'),
    'has_caret_super':     re.compile(r'[A-Za-z0-9}\)]\^[A-Za-z0-9{(\-]'),
    'has_underscore_sub':  re.compile(r'[A-Za-z0-9}\)]_[A-Za-z0-9{(\-]'),
    'has_inline_dollar':   re.compile(r'\$[^\$\n]{1,200}\$'),
    'has_doubledollar':    re.compile(r'\$\$'),
    'has_set_braces':      re.compile(r'\\\{|\\\}'),
    'has_mathrm_units':    re.compile(r'\\mathrm\{(?:cm|m|kg|s|N|J|V|A|Hz|mol|K)\}'),
    'has_chemistry':       re.compile(r'\\mathrm\{[A-Z][a-zA-Z]*\}|\\rightarrow|\\rightleftharpoons'),
    'has_begin_env':       re.compile(r'\\begin\{'),
    'has_cases_env':       re.compile(r'\\begin\{cases\}'),
    'has_eta_orphan':      re.compile(r'(?<![\\A-Za-z])eta\b'),
    'has_rac_orphan':      re.compile(r'(?<![A-Za-z])rac\{'),
    'has_ext_orphan':      re.compile(r'(?<![\\A-Za-z])ext\{'),
    'has_alphaeta_glued':  re.compile(r'alphaeta\b'),
    'has_html_tag':        re.compile(r'<(table|tr|td|th|p|strong|br|thead|tbody|div|span)\b', re.I),
    'has_underscore_blank':re.compile(r'_{3,}'),
    'has_currency_amount': re.compile(r'\$\s*\d+(?:[,.]\d+)*\b'),
    'has_text_in_math':    re.compile(r'\\text\{\\?(sqrt|alpha|beta|frac)'),
    'has_n_escape':        re.compile(r'\\n[^a-zA-Z]'),
    'has_combining':       re.compile(r'[̀-ͯ]'),
    'starts_with_cmd':     re.compile(r'^\s*\\[a-zA-Z]+'),
    'has_circ':            re.compile(r'\\circ\b'),
    'has_inf':             re.compile(r'\\infty\b'),
    'has_interval':        re.compile(r'[\(\[]\s*-?[\d\\a-zA-Z][^\[\]\(\)]{0,80}[,;][^\[\]\(\)]{0,80}[\)\]]'),
    'has_implies':         re.compile(r'\\implies|\\Rightarrow|\\therefore'),
    'has_amp_in_eqn':      re.compile(r'\\\\|\&'),
    'all_letters_short':   re.compile(r'^[A-Za-z][A-Za-z ,.\-]{1,30}$'),
}

def unbalanced_dollar(s):
    n=0; i=0
    while i < len(s):
        c=s[i]
        if c == '\\' and i+1 < len(s):
            i += 2; continue
        if c == '$': n += 1
        i += 1
    return n % 2 == 1

def unbalanced_braces(s):
    bal=0; i=0
    while i < len(s):
        c=s[i]
        if c == '\\' and i+1 < len(s):
            i += 2; continue
        if c == '{': bal += 1
        elif c == '}':
            bal -= 1
            if bal < 0: return True
        i += 1
    return bal != 0

cat_pat = defaultdict(Counter)
cat_surf = defaultdict(Counter)
cat_total = Counter()
surf_total = Counter()

with open('classified_candidates.jsonl','r',encoding='utf-8') as f:
    for line in f:
        try:
            row = json.loads(line)
        except:
            continue
        cat = row.get('category','')
        cat_total[cat] += 1
        t = row.get('raw_text','') or ''
        surf = row.get('ui_surface','?')
        cat_surf[cat][surf] += 1
        surf_total[surf] += 1
        if cat in BROKEN_CATS or cat in TRICKY:
            for name, p in probes.items():
                if p.search(t):
                    cat_pat[cat][name] += 1
            if unbalanced_dollar(t): cat_pat[cat]['unbalanced_dollar'] += 1
            if unbalanced_braces(t): cat_pat[cat]['unbalanced_braces'] += 1

lines = []
lines.append('### Category totals ###')
for k,v in cat_total.most_common():
    lines.append(f'  {k}: {v}')

lines.append('')
lines.append('### UI surface totals ###')
for k,v in surf_total.most_common():
    lines.append(f'  {k}: {v}')

lines.append('')
lines.append('### Category x UI-surface ###')
for cat in sorted(cat_total, key=lambda k: -cat_total[k]):
    if cat in BROKEN_CATS or cat in TRICKY:
        lines.append(f'\n* {cat} (n={cat_total[cat]})')
        for surf, n in cat_surf[cat].most_common():
            lines.append(f'    {surf}: {n}  ({n*100.0/cat_total[cat]:.1f}%)')

lines.append('')
lines.append('### Pattern frequencies per failure category ###')
for cat, cnt in cat_pat.items():
    n = cat_total[cat]
    lines.append(f'\n* {cat} (n={n})')
    for k,v in cnt.most_common():
        lines.append(f'    {k}: {v}  ({v*100.0/n:.1f}%)')

with open('_probe_full_out.txt','w',encoding='utf-8') as out:
    out.write('\n'.join(lines))
print('done')
