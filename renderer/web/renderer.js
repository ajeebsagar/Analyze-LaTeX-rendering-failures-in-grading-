/**
 * Browser-side port of the Python pipeline.
 * Mirrors pipeline/{segmenter,classifier,repair,validator,renderer}.py closely.
 *
 * Exports:  window.LatexRenderer.prepare(text, {sourceFamily}) -> {html, preparedText, segments, repairs, failures}
 */
(function (global) {
  'use strict';

  // ---- Constants ----
  var MATH_COMMANDS = new Set([
    'frac','sqrt','alpha','beta','gamma','delta','epsilon','theta','lambda','mu','nu','pi',
    'rho','sigma','tau','phi','chi','psi','omega','varepsilon','vartheta','varphi','Delta',
    'Sigma','Omega','Pi','Gamma','Lambda','Phi','Psi','Theta','infty','sum','prod','int',
    'lim','log','ln','sin','cos','tan','cot','sec','csc','arcsin','arccos','arctan','le','ge',
    'leq','geq','neq','ne','approx','equiv','propto','in','notin','subset','subseteq','supset',
    'supseteq','cap','cup','to','rightarrow','Rightarrow','implies','iff','Leftrightarrow',
    'leftarrow','Leftarrow','rightleftharpoons','cdot','times','div','pm','mp','ast','left',
    'right','big','Big','bigg','Bigg','mathrm','mathbf','mathbb','mathcal','mathit','mathsf',
    'text','begin','end','vec','hat','bar','tilde','dot','ddot','overline','underline','binom',
    'tfrac','dfrac','circ','degree','prime','therefore','because'
  ]);

  var FORBIDDEN_COMMANDS = new Set([
    'input','include','write','openout','closeout','immediate','csname','endcsname','loop',
    'repeat','newif','href','url','includegraphics'
  ]);

  var SOURCE_MATH_PRIOR = {
    'rubric_criterion': 0.85, 'rubric_description': 0.45, 'graded_step_working_line': 0.6,
    'graded_step_student_work': 0.5, 'review_working_line': 0.55, 'annotation_error_text': 0.55,
    'annotation_other': 0.4, 'feedback': 0.25, 'graded_step_desc': 0.3,
    'graded_step_explanation': 0.25, 'ai_solution': 0.25, 'ai_answer': 0.45,
    'expected_answer': 0.45, 'student_answer': 0.15, 'authored_question': 0.2,
    'question_short_prompt': 0.2
  };

  var MAX_LENGTH = 8000, MAX_BRACE_DEPTH = 32;
  var RENDER_CONFIDENCE_THRESHOLD = 0.55;
  var REPAIR_CONFIDENCE_THRESHOLD = 0.7;

  // ---- Helpers ----
  function htmlEscape(s){
    return String(s).replace(/[&<>"']/g, function(c){
      return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c];
    });
  }

  function countUnescapedDollars(s){
    var n=0, i=0;
    while (i < s.length){
      if (s[i] === '\\' && i+1 < s.length){ i+=2; continue; }
      if (s[i] === '$') n++;
      i++;
    }
    return n;
  }

  function findUnescapedDollar(s, start){
    var i=start, n=s.length;
    while (i < n){
      if (s[i] === '\\' && i+1 < n){ i+=2; continue; }
      if (s[i] === '$') return i;
      i++;
    }
    return -1;
  }

  // ---- Segmenter ----
  function segment(text){
    if (!text) return [];
    var oddDollar = (countUnescapedDollars(text) % 2 === 1);
    var totalDollars = oddDollar ? countUnescapedDollars(text) : 0;
    var out=[], bufStart=0, i=0, n=text.length, seenDollars=0;

    function flushText(upto){
      if (upto > bufStart) out.push({kind:'text', content:text.slice(bufStart, upto), start:bufStart, end:upto});
    }

    while (i < n){
      var c = text[i];
      if (c === '\\' && i+1 < n && text[i+1] === '$'){ i+=2; continue; }
      if (c === '\\' && i+1 < n && '()[]'.indexOf(text[i+1]) >= 0){
        var opener = text.substr(i,2);
        var close = (opener === '\\(') ? '\\)' : (opener === '\\[' ? '\\]' : null);
        if (close === null){ i+=2; continue; }
        var j = text.indexOf(close, i+2);
        if (j === -1){ i+=2; continue; }
        flushText(i);
        out.push({kind: opener === '\\(' ? 'math_paren':'math_bracket',
                  content:text.slice(i+2, j), start:i, end:j+2});
        i = j+2; bufStart = i; continue;
      }
      if (c === '$' && i+1 < n && text[i+1] === '$'){
        var j2 = text.indexOf('$$', i+2);
        if (j2 === -1){ i+=2; continue; }
        flushText(i);
        out.push({kind:'math_display', content:text.slice(i+2, j2), start:i, end:j2+2});
        seenDollars += 2;
        i = j2+2; bufStart = i; continue;
      }
      if (c === '$'){
        seenDollars++;
        if (oddDollar && seenDollars === totalDollars){ i++; continue; }
        var j3 = findUnescapedDollar(text, i+1);
        if (j3 === -1){ i++; continue; }
        flushText(i);
        out.push({kind:'math_inline', content:text.slice(i+1, j3), start:i, end:j3+1});
        seenDollars++;
        i = j3+1; bufStart = i; continue;
      }
      i++;
    }
    flushText(n);
    return out;
  }

  // ---- Classifier ----
  var RE_COMMAND = /\\([a-zA-Z]+)/g;
  var RE_SUPER = /[A-Za-z0-9}\)\]]\^[A-Za-z0-9{(\-]/g;
  var RE_SUB   = /[A-Za-z0-9}\)\]]_[A-Za-z0-9{(\-]/g;
  var RE_ORPHAN_ETA = /(^|[^\\A-Za-z])eta\b/;
  var RE_ORPHAN_RAC = /(^|[^A-Za-z])rac\{/;
  var RE_ORPHAN_EXT = /(^|[^\\A-Za-z])ext\{/;
  var RE_ALPHAETA = /(^|[^\\A-Za-z])alphaeta\b/;
  var RE_CURRENCY = /^\s*\d+(?:[,.]\d+)*\s*(?:[A-Za-z]{1,15}(?:\s+[A-Za-z]{1,15}){0,3})?\s*$/;
  var RE_PURE_ALPHA = /^[A-Za-z]{1,15}$/;
  var RE_HTML = /<(table|tr|td|th|p|strong|br|thead|tbody|div|span)\b/i;
  var RE_FILL_BLANK = /_{3,}/;
  var RE_OPERATOR = /[+\-*/=<>^_]/g;
  var RE_DIGIT = /\d/g;

  function classify(content, opts){
    opts = opts || {};
    var insideDelim = !!opts.insideDelim;
    var src = opts.sourceFamily || 'unknown';

    if (RE_HTML.test(content)) return {score:0, isMath:false, isHtml:true, isCurrency:false, isFillBlank:false, corruption:false, signals:{html:true}};
    if (RE_FILL_BLANK.test(content) && !insideDelim) return {score:0, isMath:false, isHtml:false, isCurrency:false, isFillBlank:true, corruption:false, signals:{fillBlank:true}};

    var corruption = false, hits=[];
    if (RE_ORPHAN_ETA.test(content)){ corruption=true; hits.push('eta'); }
    if (RE_ORPHAN_RAC.test(content)){ corruption=true; hits.push('rac'); }
    if (RE_ORPHAN_EXT.test(content)){ corruption=true; hits.push('ext'); }
    if (RE_ALPHAETA.test(content)){ corruption=true; hits.push('alphaeta'); }

    var isCurrency = RE_CURRENCY.test(content) && !insideDelim;
    if (isCurrency) return {score:0.05, isMath:false, isHtml:false, isCurrency:true, isFillBlank:false, corruption:corruption, signals:{currency:true}};

    var cmds = [], m;
    RE_COMMAND.lastIndex=0;
    while ((m = RE_COMMAND.exec(content))) cmds.push(m[1]);
    var knownCmds = cmds.filter(function(c){ return MATH_COMMANDS.has(c); });

    var nSuper = (content.match(RE_SUPER) || []).length;
    var nSub   = (content.match(RE_SUB)   || []).length;
    var nOp    = (content.match(RE_OPERATOR) || []).length;
    var nDigit = (content.match(RE_DIGIT) || []).length;
    var pureAlpha = RE_PURE_ALPHA.test(content.trim());

    var score = 0;
    if (insideDelim) score += 0.6;
    score += (SOURCE_MATH_PRIOR[src] || 0.3) * 0.15;
    score += Math.min(0.35, 0.12 * knownCmds.length);
    score += Math.min(0.15, 0.05 * (nSuper + nSub));
    if (nOp >= 2 && nDigit >= 1) score += 0.1;
    if (corruption) score += 0.15;
    if (pureAlpha && !insideDelim) score -= 0.4;
    score = Math.max(0, Math.min(1, score));

    return {
      score: score, isMath: score >= RENDER_CONFIDENCE_THRESHOLD,
      isHtml:false, isCurrency:false, isFillBlank:false,
      corruption: corruption,
      signals:{ knownCommands: knownCmds.length, super:nSuper, sub:nSub, ops:nOp, digits:nDigit, corruptionHits:hits }
    };
  }

  // ---- Repairs ----
  function tier1Global(text){
    var repairs = [];
    var nfc = text.normalize ? text.normalize('NFC') : text;
    if (nfc !== text) repairs.push('nfc_normalize');
    return [nfc, repairs];
  }

  var COMBINING_RE = /[̀-ͯ]/g;
  function tier1MathSegment(content){
    var repairs = [];
    var stripped = content.replace(COMBINING_RE, '');
    if (stripped !== content) repairs.push('strip_combining_diacritics');
    return [stripped, repairs];
  }

  function tier1ProseSegment(content){
    var repairs = [];
    var out = content.replace(/\\n(?=[A-Z]|\s|$)/g, '\n').replace(/\\t(?=\s|$)/g, '\t');
    if (out !== content) repairs.push('literal_escape_to_whitespace');
    return [out, repairs];
  }

  function tier2OrphanBackslash(content){
    var repairs = [];
    var out = content;

    var before = out;
    out = out.replace(/(^|[^A-Za-z\\])alphaeta\b/g, '$1\\alpha\\beta');
    if (out !== before) repairs.push('repair_alphaeta');

    // eta -> \beta with context check
    before = out;
    out = out.replace(/(^|[^A-Za-z\\])(eta)\b/g, function(_, pre, m, idx, full){
      var start = idx + pre.length;
      var ctx = full.slice(Math.max(0, start-12), Math.min(full.length, start+m.length+12));
      if (/\\[a-zA-Z]+|\\frac|\\alpha|\\gamma|[\\{}=^_]|[+\-=]/.test(ctx)) return pre + '\\beta';
      return pre + m;
    });
    if (out !== before) repairs.push('repair_orphan_eta_to_beta');

    before = out;
    out = out.replace(/(^|[^A-Za-z\\])(beta|gamma|theta|alpha|delta|phi|psi|omega|sigma|lambda)\b/g,
      function(_, pre, name, idx, full){
        var start = idx + pre.length;
        var ctx = full.slice(Math.max(0, start-12), Math.min(full.length, start+name.length+12));
        if (/\\[a-zA-Z]+|\\frac|[\\{}=^_]/.test(ctx)) return pre + '\\' + name;
        return pre + name;
      });
    if (out !== before) repairs.push('repair_orphan_greek');

    before = out;
    out = out.replace(/(^|[^A-Za-z\\])rac(\{[^{}]*\}\{[^{}]*\})/g, '$1\\frac$2');
    if (out !== before) repairs.push('repair_orphan_rac');

    before = out;
    out = out.replace(/(^|[^A-Za-z\\])ext(\{[^{}]*\})/g, '$1\\text$2');
    if (out !== before) repairs.push('repair_orphan_ext');

    return [out, repairs];
  }

  var LOOKS_MATH_ONLY = /^[\s\d+\-*/=<>(){}\[\].,;:|^_!?\\a-zA-Z]+$/;
  function tier2WrapMathOnly(content, opts){
    opts = opts || {};
    var prior = opts.familyPrior == null ? 0.3 : opts.familyPrior;
    var s = content.trim();
    if (!s) return [content, [], false];
    if (s.indexOf('\\(') >= 0 || s.indexOf('\\[') >= 0) return [content, [], false];
    if (prior < 0.5) return [content, [], false];

    // Handle orphan-dollar truncation: count unescaped $ chars
    var nDollars = countUnescapedDollars(s);
    if (nDollars >= 2) return [content, [], false];   // mixed prose+math already
    var candidate = s;
    var repairName = 'wrap_math_only';
    if (nDollars === 1) {
      var idx = findUnescapedDollar(s, 0);
      if (idx === 0) {
        candidate = s.slice(1).replace(/^\s+/, '');
      } else if (idx === s.length - 1) {
        candidate = s.slice(0, -1).replace(/\s+$/, '');
      } else {
        return [content, [], false];
      }
      repairName = 'wrap_math_only_strip_orphan_dollar';
    }
    if (!candidate) return [content, [], false];
    if (!LOOKS_MATH_ONLY.test(candidate)) return [content, [], false];

    var hasCmd = false;
    for (var i=0; i<candidate.length; i++){
      if (candidate[i] === '\\' && /[a-zA-Z]/.test(candidate[i+1] || '')){
        var j=i+1, name='';
        while (j<candidate.length && /[a-zA-Z]/.test(candidate[j])){ name+=candidate[j]; j++; }
        if (MATH_COMMANDS.has(name)){ hasCmd=true; break; }
      }
    }
    var hasSupSub = /[A-Za-z0-9}\)\]][\^_][A-Za-z0-9{(\-]/.test(candidate);
    var hasSetBraces = /\\\{|\\\}/.test(candidate);
    if (!hasCmd && !hasSupSub && !hasSetBraces) return [content, [], false];

    var lead = content.slice(0, content.length - content.replace(/^\s+/, '').length);
    var trail = content.slice(content.replace(/\s+$/, '').length);
    return [lead + '$' + candidate + '$' + trail, [repairName], true];
  }

  // ---- Validator ----
  function validate(c){
    var reasons = [];
    if (!c || !c.trim()) return {ok:false, reasons:['empty_math_segment']};
    if (c.length > MAX_LENGTH) reasons.push('exceeds_max_length');
    var depth=0, maxd=0, i=0, n=c.length;
    while (i<n){
      var ch = c[i];
      if (ch === '\\' && i+1 < n){ i+=2; continue; }
      if (ch === '{'){ depth++; if (depth>maxd) maxd=depth; }
      else if (ch === '}'){ depth--; if (depth<0){ reasons.push('unbalanced_close_brace'); break; } }
      i++;
    }
    if (depth !== 0 && reasons.indexOf('unbalanced_close_brace') < 0) reasons.push('unbalanced_brace_count');
    if (maxd > MAX_BRACE_DEPTH) reasons.push('brace_depth_exceeded');
    if (/_{3,}/.test(c)) reasons.push('subscript_run_too_long');
    var m, rgx = /\\([a-zA-Z]+)/g;
    while ((m = rgx.exec(c))){
      if (FORBIDDEN_COMMANDS.has(m[1])){ reasons.push('forbidden_command:' + m[1]); break; }
    }
    return {ok: reasons.length === 0, reasons: reasons};
  }

  // ---- Renderer ----
  function fallbackSpan(content, reason){
    return '<span class="latex-fallback" data-render-reason="'+htmlEscape(reason)+'">'+htmlEscape(content)+'</span>';
  }

  function reDelim(kind, content){
    if (kind === 'math_display')  return '$$'+content+'$$';
    if (kind === 'math_paren')    return '\\('+content+'\\)';
    if (kind === 'math_bracket')  return '\\['+content+'\\]';
    return '$'+content+'$';
  }

  function mathPlaceholder(kind, prepared){
    var mode = (kind === 'math_display' || kind === 'math_bracket') ? 'display' : 'inline';
    return '<span class="latex-math" data-math="'+mode+'">'+prepared+'</span>';
  }

  function processSegment(seg, familyPrior){
    if (seg.kind === 'text'){
      var pr = tier1ProseSegment(seg.content);
      var html = htmlEscape(pr[0]).replace(/\n/g, '<br>');
      return {kind:seg.kind, original:seg.content, repaired:pr[0], repairs:pr[1],
              prepared:pr[0], html:html, outcome:'text', classification:{score:0, isMath:false}};
    }
    var cls = classify(seg.content, {insideDelim:true});
    var repairs = [];
    var r1 = tier1MathSegment(seg.content); var content = r1[0]; repairs = repairs.concat(r1[1]);
    if (cls.corruption || cls.score >= REPAIR_CONFIDENCE_THRESHOLD || true){
      var r2 = tier2OrphanBackslash(content); content = r2[0]; repairs = repairs.concat(r2[1]);
    }
    var cls2 = classify(content, {insideDelim:true});
    var v = validate(content);
    if (!v.ok){
      var prepared = reDelim(seg.kind, content);
      return {kind:seg.kind, original:seg.content, repaired:content, repairs:repairs,
              prepared:prepared, html:fallbackSpan(prepared, v.reasons.join(';')),
              outcome:'fallback', classification:cls2, validation:v};
    }
    var prepared2 = reDelim(seg.kind, content);
    return {kind:seg.kind, original:seg.content, repaired:content, repairs:repairs,
            prepared:prepared2, html:mathPlaceholder(seg.kind, prepared2),
            outcome:'math', classification:cls2};
  }

  function prepare(text, opts){
    opts = opts || {};
    var fam = opts.sourceFamily || 'unknown';
    var prior = SOURCE_MATH_PRIOR[fam] || 0.3;
    if (text == null) text = '';

    if (RE_HTML.test(text)){
      return {
        preparedText: text,
        html: fallbackSpan(text, 'html_content'),
        segments: [{kind:'html', original:text, repaired:text, repairs:[], outcome:'fallback'}],
        repairs: [], failures:['html_content']
      };
    }

    var g = tier1Global(text);
    text = g[0]; var allRepairs = g[1].slice();
    var w = tier2WrapMathOnly(text, {familyPrior: prior});
    text = w[0]; allRepairs = allRepairs.concat(w[1]);

    var segs = segment(text);
    var prepared = [], html = [], outSegs = [], failures = [];
    for (var i=0;i<segs.length;i++){
      var sr = processSegment(segs[i], prior);
      prepared.push(sr.prepared);
      html.push(sr.html);
      outSegs.push(sr);
      allRepairs = allRepairs.concat(sr.repairs);
      if (sr.validation && !sr.validation.ok) failures = failures.concat(sr.validation.reasons);
    }
    return {
      preparedText: prepared.join(''),
      html: html.join(''),
      segments: outSegs,
      repairs: allRepairs,
      failures: failures
    };
  }

  global.LatexRenderer = { prepare: prepare, segment: segment, classify: classify, validate: validate };
})(window);
