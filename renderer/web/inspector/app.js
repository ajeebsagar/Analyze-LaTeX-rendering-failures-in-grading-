/* Inspector — single-page observability UI for the LaTeX pipeline.
 *
 * Loads ./data.json produced by app/build_inspector.py, renders a dashboard,
 * filterable row list, and a per-row pipeline whiteboard trace. Math is
 * rendered with KaTeX (auto-render).
 */
(function () {
  'use strict';

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));
  const KATEX_OPTS = {
    delimiters: [
      { left: '$$', right: '$$', display: true },
      { left: '$',  right: '$',  display: false },
      { left: '\\[', right: '\\]', display: true },
      { left: '\\(', right: '\\)', display: false }
    ],
    throwOnError: false,
    strict: 'ignore'
  };

  // -------- App state --------
  const state = {
    data: null,
    filters: {
      outcome: new Set(),
      bucket: new Set(),
      repair: new Set(),
      family: new Set(),
      surface: new Set(),
      category: new Set()
    },
    search: '',
    sort: 'default',
    selectedId: null,
  };

  // -------- Bootstrap --------
  fetch('./data.json')
    .then((r) => {
      if (!r.ok) throw new Error('Failed to load data.json (HTTP ' + r.status + ')');
      return r.json();
    })
    .then((data) => {
      state.data = data;
      renderAll();
    })
    .catch((err) => {
      $('#rows-list').innerHTML =
        '<div class="empty-state">' +
        '<strong>Could not load data.json</strong><br><br>' +
        'Run this first:<br><code>python -m app.build_inspector --input ../classified_candidates.jsonl</code><br><br>' +
        'Or serve over HTTP (browsers block fetch on file://):<br>' +
        '<code>python -m http.server 8000</code> then open <code>http://localhost:8000/web/inspector/index.html</code><br><br>' +
        'Error: ' + err.message + '</div>';
    });

  // -------- Main render --------
  function renderAll() {
    renderMetaLine();
    renderDashboard();
    renderFilters();
    renderRows();
    // Auto-select first row for the whiteboard demo
    if (state.data.rows.length) {
      selectRow(state.data.rows[0].id);
    }
    // Wire live heal
    setupLiveHeal();
    runLiveHeal();
    // Wire global handlers
    $('#search').addEventListener('input', (e) => {
      state.search = e.target.value.toLowerCase().trim();
      renderRows();
    });
    $('#reset-filters').addEventListener('click', () => {
      Object.values(state.filters).forEach((s) => s.clear());
      state.search = '';
      $('#search').value = '';
      renderFilters();
      renderRows();
    });
    $('#sort-by').addEventListener('change', (e) => {
      state.sort = e.target.value;
      renderRows();
    });
  }

  function renderMetaLine() {
    const m = state.data.meta;
    $('#meta-line').textContent =
      `loaded ${state.data.rows.length} rows  · input: ${m.input_path}  · generated ${m.generated_at}`;
  }

  // -------- Dashboard --------
  function renderDashboard() {
    const s = state.data.meta.summary;
    $('#stat-total').textContent = state.data.rows.length.toLocaleString();
    $('#stat-math').textContent = s.n_math.toLocaleString();
    $('#stat-repair').textContent = s.n_repair.toLocaleString();
    $('#stat-fallback').textContent = s.n_fallback.toLocaleString();

    renderBarChart('#bucket-chart', s.bucket_counts, (k) =>
      `${k} ${s.bucket_descriptions?.[k] ? '· ' + s.bucket_descriptions[k] : ''}`);
    renderBarChart('#repair-chart', s.repair_counts);
    renderBarChart('#family-chart', s.family_counts);
  }

  function renderBarChart(sel, counts, labelFn) {
    const root = $(sel);
    root.innerHTML = '';
    const entries = Object.entries(counts).slice(0, 8);
    if (!entries.length) {
      root.innerHTML = '<div style="color:#94a3b8;font-size:11px">(no data)</div>';
      return;
    }
    const max = Math.max(...entries.map((e) => e[1]));
    entries.forEach(([k, v]) => {
      const row = document.createElement('div');
      row.className = 'bar-row';
      row.innerHTML = `
        <div class="bar-label" title="${escapeHtml(labelFn ? labelFn(k) : k)}">${escapeHtml(labelFn ? labelFn(k) : k)}</div>
        <div class="bar-track"><div class="bar-fill" style="width:${(v/max)*100}%"></div></div>
        <div class="bar-count">${v.toLocaleString()}</div>`;
      root.appendChild(row);
    });
  }

  // -------- Filters --------
  function renderFilters() {
    const s = state.data.meta.summary;
    const facets = [
      ['#filter-outcome',  'outcome',  s.outcome_counts],
      ['#filter-bucket',   'bucket',   s.bucket_counts],
      ['#filter-repair',   'repair',   s.repair_counts],
      ['#filter-family',   'family',   s.family_counts],
      ['#filter-surface',  'surface',  s.ui_surface_counts],
      ['#filter-category', 'category', s.category_counts]
    ];
    facets.forEach(([sel, group, counts]) => {
      const root = $(sel);
      root.innerHTML = '';
      Object.entries(counts).forEach(([k, v]) => {
        const chip = document.createElement('button');
        chip.type = 'button';
        chip.className = 'chip';
        chip.dataset.key = `${group}:${k}`;
        if (state.filters[group].has(k)) chip.classList.add('active');
        chip.innerHTML = `${escapeHtml(k)} <span class="count">${v}</span>`;
        chip.addEventListener('click', () => {
          if (state.filters[group].has(k)) state.filters[group].delete(k);
          else state.filters[group].add(k);
          renderFilters();
          renderRows();
        });
        root.appendChild(chip);
      });
    });
  }

  // -------- Rows list --------
  function rowMatchesFilters(row) {
    const f = state.filters;
    if (f.outcome.size && !f.outcome.has(row.outcome)) return false;
    if (f.bucket.size && !row.buckets.some((b) => f.bucket.has(b))) return false;
    if (f.repair.size && !row.repairs.some((r) => f.repair.has(r))) return false;
    if (f.family.size && !f.family.has(row.family)) return false;
    if (f.surface.size && !f.surface.has(row.ui_surface)) return false;
    if (f.category.size && !f.category.has(row.category)) return false;
    if (state.search) {
      const hay = (
        row.id + ' ' + (row.raw || '') + ' ' + row.repairs.join(' ') +
        ' ' + row.family + ' ' + row.ui_surface + ' ' + row.category
      ).toLowerCase();
      if (!hay.includes(state.search)) return false;
    }
    return true;
  }

  function sortedRows(rows) {
    switch (state.sort) {
      case 'repairs': return [...rows].sort((a,b) => b.repairs.length - a.repairs.length);
      case 'fallback': return [...rows].sort((a,b) => Number(b.had_fallback) - Number(a.had_fallback));
      case 'length': return [...rows].sort((a,b) => (b.raw||'').length - (a.raw||'').length);
      default: return rows;
    }
  }

  function renderRows() {
    const filtered = state.data.rows.filter(rowMatchesFilters);
    const sorted = sortedRows(filtered);
    $('#rows-summary').textContent = `Showing ${sorted.length} of ${state.data.rows.length} rows`;
    const list = $('#rows-list');
    list.innerHTML = '';
    if (!sorted.length) {
      list.innerHTML = '<div class="empty-state">No rows match the current filters.</div>';
      return;
    }
    // Render at most 200 rows for performance; user can filter to find more.
    const RENDER_CAP = 200;
    sorted.slice(0, RENDER_CAP).forEach((row) => list.appendChild(rowCard(row)));
    if (sorted.length > RENDER_CAP) {
      const note = document.createElement('div');
      note.className = 'empty-state';
      note.textContent = `(${sorted.length - RENDER_CAP} more rows — refine filters to see them)`;
      list.appendChild(note);
    }
  }

  function rowCard(row) {
    const card = document.createElement('div');
    card.className = `row-card outcome-${row.outcome}`;
    if (row.id === state.selectedId) card.classList.add('expanded');
    card.dataset.id = row.id;

    const header = document.createElement('div');
    header.className = 'row-header';
    header.innerHTML = `
      <div class="row-id">${escapeHtml(row.id)}</div>
      <div>
        <div class="row-summary">
          <span class="outcome-badge ${row.outcome}">${row.outcome}</span>
          ${row.buckets.map((b) => `<span class="bucket-chip" title="${escapeHtml((state.data.meta.summary.bucket_descriptions||{})[b]||'')}">${b}</span>`).join('')}
          ${row.repairs.map((r) => `<span class="repair-chip">${escapeHtml(r)}</span>`).join('')}
          <span class="family-tag">${escapeHtml(row.family || '?')}</span>
          <span class="family-tag">${escapeHtml(row.ui_surface || '?')}</span>
        </div>
        <div class="row-raw">${escapeHtml(truncate(row.raw, 280))}</div>
      </div>
      <div class="row-chevron">${row.id === state.selectedId ? '▾' : '▸'}</div>`;
    header.addEventListener('click', () => {
      if (state.selectedId === row.id) state.selectedId = null;
      else selectRow(row.id);
      renderRows();
    });
    card.appendChild(header);

    if (row.id === state.selectedId) {
      card.appendChild(rowDetail(row));
    }
    return card;
  }

  function rowDetail(row) {
    const wrap = document.createElement('div');
    wrap.className = 'row-detail';
    wrap.innerHTML = `
      <div class="detail-grid">
        <div class="detail-block">
          <div class="detail-block-title">Original input (from DB)</div>
          <pre>${escapeHtml(row.raw || '')}</pre>
        </div>
        <div class="detail-block">
          <div class="detail-block-title">Healed / prepared text (KaTeX-ready)</div>
          <pre>${escapeHtml(row.prepared || '')}</pre>
        </div>
        <div class="detail-block">
          <div class="detail-block-title">Rendered output (KaTeX)</div>
          <div class="rendered render-target">${row.html}</div>
        </div>
        <div class="detail-block">
          <div class="detail-block-title">Pipeline trace</div>
          <div style="font-size:12px;color:#475569">
            <div><strong>Buckets:</strong> ${row.buckets.map((b) => `<span class="bucket-chip" title="${escapeHtml((state.data.meta.summary.bucket_descriptions||{})[b]||'')}">${b}: ${escapeHtml((state.data.meta.summary.bucket_descriptions||{})[b]||'?')}</span>`).join(' ')}</div>
            <div style="margin-top:6px"><strong>Repairs:</strong> ${row.repairs.length ? row.repairs.map((r)=>`<span class="repair-chip">${escapeHtml(r)}</span>`).join(' ') : '<em>(none)</em>'}</div>
            <div style="margin-top:6px"><strong>Validation failures:</strong> ${row.failure_reasons.length ? row.failure_reasons.map((r)=>`<code>${escapeHtml(r)}</code>`).join(' ') : '<em>(none)</em>'}</div>
            <div style="margin-top:6px"><strong>Source:</strong> <code>${escapeHtml(row.field_path || '?')}</code></div>
            <div style="margin-top:6px"><strong>Tenant:</strong> <code>${escapeHtml(row.tenant || '?')}</code> · <strong>Subject:</strong> <code>${escapeHtml(row.subject || '?')}</code> · <strong>Grade:</strong> <code>${escapeHtml(row.grade || '?')}</code></div>
          </div>
        </div>
      </div>
      <div class="segment-list">
        <div class="detail-block-title" style="margin:10px 0 4px">Per-segment trace (${row.segments.length} segments)</div>
        ${row.segments.map(segmentCard).join('')}
      </div>`;
    // Defer KaTeX auto-render to after DOM insertion
    setTimeout(() => {
      const target = wrap.querySelector('.render-target');
      if (target && window.renderMathInElement) {
        window.renderMathInElement(target, KATEX_OPTS);
      }
    }, 0);
    return wrap;
  }

  function segmentCard(seg) {
    const repaired = seg.repaired !== seg.original;
    const signalsList = Object.entries(seg.signals || {})
      .map(([k,v]) => `<span class="signal-pill">${escapeHtml(k)}=${escapeHtml(JSON.stringify(v))}</span>`)
      .join('');
    return `
      <div class="segment-card outcome-${seg.outcome}">
        <div class="segment-head">
          <span class="kind">${escapeHtml(seg.kind)}</span>
          <span class="score">score=${seg.score}</span>
          <span class="outcome-tag ${seg.outcome}">${seg.outcome}</span>
        </div>
        <div class="segment-row"><span class="label">Original</span><span class="val">${escapeHtml(seg.original)}</span></div>
        ${repaired ? `<div class="segment-row"><span class="label">Repaired</span><span class="val diff">${escapeHtml(seg.repaired)}</span></div>` : ''}
        ${seg.prepared ? `<div class="segment-row"><span class="label">Prepared</span><span class="val">${escapeHtml(seg.prepared)}</span></div>` : ''}
        ${seg.repairs.length ? `<div class="segment-row"><span class="label">Repairs</span><span class="val">${seg.repairs.map((r)=>`<span class="repair-chip">${escapeHtml(r)}</span>`).join(' ')}</span></div>` : ''}
        ${seg.validation_reasons.length ? `<div class="segment-row"><span class="label">Validation</span><span class="val">${seg.validation_reasons.map((r)=>`<code>${escapeHtml(r)}</code>`).join(' ')}</span></div>` : ''}
        ${signalsList ? `<div class="segment-row"><span class="label">Signals</span><span class="val"><div class="signal-pills">${signalsList}</div></span></div>` : ''}
      </div>`;
  }

  // -------- Whiteboard --------
  function selectRow(id) {
    state.selectedId = id;
    const row = state.data.rows.find((r) => r.id === id);
    if (!row) return;
    $('#current-id').textContent = id;
    $('#current-buckets').innerHTML = row.buckets.map((b) =>
      `<span class="bucket-chip" title="${escapeHtml((state.data.meta.summary.bucket_descriptions||{})[b]||'')}">${b}</span>`
    ).join(' ');

    // Mark which stages fired
    const stages = {
      detect: 'fired',  // always fires
      classify: row.segments.some((s) => s.kind.startsWith('math')) ? 'fired' : 'skipped',
      repair: row.repairs.length ? 'fired' : 'skipped',
      validate: row.had_fallback ? 'failed' : 'fired',
      render: row.had_math ? 'fired' : 'skipped',
      fallback: row.had_fallback ? 'fired' : 'skipped'
    };
    Object.entries(stages).forEach(([stage, status]) => {
      const node = document.querySelector(`.stage[data-stage="${stage}"]`);
      node.classList.remove('fired','skipped','failed');
      node.classList.add(status);
      $(`#stage-${stage}`).textContent = stageStatusText(stage, status, row);
    });
  }

  function stageStatusText(stage, status, row) {
    if (status === 'skipped') return 'skipped';
    if (stage === 'detect') return `${row.segments.length} seg`;
    if (stage === 'classify') {
      const math = row.segments.filter((s) => s.outcome === 'math').length;
      return `${math} math span(s)`;
    }
    if (stage === 'repair') return `${row.repairs.length} repair(s)`;
    if (stage === 'validate') return status === 'failed' ? `rejected` : 'ok';
    if (stage === 'render') return `${row.segments.filter((s)=>s.outcome==='math').length} math`;
    if (stage === 'fallback') return `${row.segments.filter((s)=>s.outcome==='fallback').length} span(s)`;
    return status;
  }

  // -------- Live heal --------
  function setupLiveHeal() {
    $('#live-input').addEventListener('input', runLiveHeal);
    $('#live-family').addEventListener('change', runLiveHeal);
  }

  function runLiveHeal() {
    const text = $('#live-input').value;
    const fam = $('#live-family').value;
    if (!window.LatexRenderer) {
      $('#live-prepared').textContent = '(JS pipeline not loaded — open this page via http.server)';
      return;
    }
    const r = window.LatexRenderer.prepare(text, { sourceFamily: fam });
    $('#live-prepared').textContent = r.preparedText || '(empty)';
    const renderedBox = $('#live-rendered');
    renderedBox.innerHTML = r.html;
    if (window.renderMathInElement) {
      window.renderMathInElement(renderedBox, KATEX_OPTS);
    }
    const repairChips = (r.repairs.length
      ? r.repairs.map((rp) => `<span class="repair-chip">${escapeHtml(rp)}</span>`).join(' ')
      : '<em>(no repairs)</em>');
    const failChips = (r.failures.length
      ? r.failures.map((f) => `<code>${escapeHtml(f)}</code>`).join(' ')
      : '');
    $('#live-meta').innerHTML =
      `<strong>Repairs:</strong> ${repairChips}` +
      (failChips ? `  ·  <strong>Validation:</strong> ${failChips}` : '');
  }

  // -------- Util --------
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, (c) => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }
  function truncate(s, n) {
    s = String(s || '');
    return s.length <= n ? s : s.slice(0, n - 1) + '…';
  }
})();
