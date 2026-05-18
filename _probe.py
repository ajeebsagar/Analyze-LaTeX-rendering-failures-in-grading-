import csv, re, json
from collections import Counter

patterns = {
    'starts_with_backslash_cmd': re.compile(r'^\s*\\[a-zA-Z]+'),
    'has_frac':                   re.compile(r'\\frac\b'),
    'has_greek_letter':           re.compile(r'\\(alpha|beta|gamma|theta|pi|sigma|lambda|mu|nu|rho|delta|phi)\b'),
    'has_sqrt':                   re.compile(r'\\sqrt\b'),
    'has_caret_super':            re.compile(r'[A-Za-z0-9}\)]\^[A-Za-z0-9{(\-]'),
    'has_underscore_sub':         re.compile(r'[A-Za-z0-9}\)]_[A-Za-z0-9{(\-]'),
    'has_inline_dollar_pair':     re.compile(r'\$[^\$]+\$'),
    'has_eta_no_backslash':       re.compile(r'(?<![\\A-Za-z])eta\b'),
    'has_rac_no_backslash':       re.compile(r'(?<![A-Za-z])rac\{'),
    'has_alphaeta_glued':         re.compile(r'\\alphaeta\b|alphaeta\b'),
    'has_ext_no_backslash':       re.compile(r'(?<![\\A-Za-z])ext\{'),  # \\text → ext
    'has_text_wrapping_math':     re.compile(r'\\text\{\\?(sqrt|alpha|beta|frac)'),
    'has_html_tag':               re.compile(r'<(table|tr|td|th|p|strong|br|thead|tbody|div|span)\b', re.I),
    'has_literal_backslash_n':    re.compile(r'\\n(?![a-zA-Z])'),
    'has_set_notation_braces':    re.compile(r'\\\{|\\\}'),
    'has_chemistry_mathrm':       re.compile(r'\\mathrm\{'),
    'has_begin_env':              re.compile(r'\\begin\{'),
    'has_currency_amount':        re.compile(r'\$\s*\d+(?:[,.]\d+)*\b'),
    'has_combining_diacritic':    re.compile(r'[̀-ͯ]'),
    'has_circ_degree':            re.compile(r'\^\\circ\b|\\circ\b'),
    'has_units_paren':            re.compile(r'\\(?:mathrm|text)\{(?:cm|m|kg|s|N|J|V|A|Hz|mol|K)\}'),
    'has_interval_notation':      re.compile(r'\([^()]*-?\\?infty[^()]*\)|\[[^\[\]]*-?\\?infty[^\[\]]*\]'),
    'has_doubledollar_display':   re.compile(r'\$\$'),
    'has_cases_env':              re.compile(r'\\begin\{cases\}'),
}

def unbalanced_dollar(s):
    n=0; i=0
    while i < len(s):
        c=s[i]
        if c == '\\' and i+1 < len(s):
            i += 2; continue
        if c == '$':
            n += 1
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

def scan(path):
    counts = Counter()
    cats = Counter()
    tot = 0
    with open(path,'r',encoding='utf-8') as f:
        r = csv.DictReader(f)
        for row in r:
            t = row.get('raw_text','') or ''
            tot += 1
            cats[row.get('category','')] += 1
            for name, pat in patterns.items():
                if pat.search(t):
                    counts[name] += 1
            if unbalanced_dollar(t):  counts['unbalanced_dollar'] += 1
            if unbalanced_braces(t):  counts['unbalanced_braces'] += 1
    return tot, cats, counts

out = []
for label, path in [('confirmed_broken','confirmed_broken.csv'),
                    ('tricky','tricky_examples.csv'),
                    ('confirmed_good','confirmed_good.csv')]:
    tot, cats, cnt = scan(path)
    out.append(f'### {label} (total={tot}) ###')
    out.append('categories: ' + str(dict(cats.most_common())))
    out.append('patterns:')
    for k,v in cnt.most_common():
        out.append(f'  {k}: {v}  ({v*100.0/tot:.1f}%)')
    out.append('')

with open('_probe_out.txt','w',encoding='utf-8') as f:
    f.write('\n'.join(out))
print('done')
