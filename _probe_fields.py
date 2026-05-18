import json, re
from collections import Counter, defaultdict

# Group field_path into source families
def family(fp):
    if fp is None: return 'unknown'
    s = fp
    if '.ai_solution' in s: return 'ai_solution'
    if '.ai_answer' in s:   return 'ai_answer'
    if '.expected_answer' in s: return 'expected_answer'
    if '.short_prompt' in s or '.question_text' in s or '.options[' in s: return 'authored_question'
    if 'rubric_steps' in s and 'criterion' in s: return 'rubric_criterion'
    if 'rubric_steps' in s and 'description' in s: return 'rubric_description'
    if 'steps_breakdown' in s and 'description' in s: return 'graded_step_desc'
    if 'steps_breakdown' in s and 'student_work' in s: return 'graded_step_student_work'
    if 'steps_breakdown' in s and 'working_lines' in s: return 'graded_step_working_line'
    if 'steps_breakdown' in s and 'explanation' in s: return 'graded_step_explanation'
    if 'review_render.working_lines' in s: return 'review_working_line'
    if 'review_render.annotations' in s and 'error_text' in s: return 'annotation_error_text'
    if 'review_render.annotations' in s: return 'annotation_other'
    if 'feedback' in s: return 'feedback'
    if 'student_answer' in s: return 'student_answer'
    if 'question_short_prompt' in s: return 'question_short_prompt'
    return 'other:' + s.split('.')[-1][:30]

BROKEN = {'missing_math_delimiters','likely_math_missing_delimiters',
          'unbalanced_dollar','bad_brace_balance','katex_parse_error',
          'latex_parse_error','bad_super_or_subscript',
          'html_or_markdown_mixed_text','unsupported_latex_command',
          'display_or_mode_conflict','tricky_false_positive'}

family_by_cat = defaultdict(Counter)
fam_total = Counter()
cat_total = Counter()
with open('classified_candidates.jsonl','r',encoding='utf-8') as f:
    for line in f:
        try:
            row = json.loads(line)
        except:
            continue
        cat = row.get('category','')
        fam = family(row.get('field_path',''))
        fam_total[fam] += 1
        cat_total[cat] += 1
        if cat in BROKEN:
            family_by_cat[cat][fam] += 1

lines = []
lines.append('### Family totals ###')
for k,v in fam_total.most_common():
    lines.append(f'  {k}: {v}')

lines.append('\n### Failures by source family ###')
for cat in sorted(family_by_cat, key=lambda k: -cat_total[k]):
    lines.append(f'\n* {cat} (n={cat_total[cat]})')
    for fam, n in family_by_cat[cat].most_common():
        lines.append(f'    {fam}: {n}  ({n*100.0/cat_total[cat]:.1f}%)')

with open('_probe_fields_out.txt','w',encoding='utf-8') as o:
    o.write('\n'.join(lines))
print('done')
