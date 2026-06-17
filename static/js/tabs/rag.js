import { getStatus, getDocs, getUrlFiles, rebuildSitemap as apiRebuildSitemap, rebuildFile as apiRebuildFile } from '../core/api.js';
import { log } from '../core/logger.js';
import { showToast } from '../core/toast.js';
import { isValidUrl, setButtonLoading } from '../core/utils.js';
import { state } from '../core/state.js';

let rebuildEventSource = null;

function _clearChildren(el) {
  if (!el) return;
  while (el.firstChild) el.removeChild(el.firstChild);
}

function _formatStage(stage) {
  const s = (stage || '').toString().trim().toLowerCase();
  if (!s || s === 'idle') return 'Idle';
  if (s === 'starting') return 'Starting…';
  if (s === 'crawling') return 'Crawling…';
  if (s === 'chunking') return 'Chunking…';
  if (s === 'embedding') return 'Embedding…';
  if (s === 'duckdb_init') return 'Initializing DuckDB…';
  if (s === 'duckdb_insert') return 'Writing chunks…';
  if (s === 'done') return 'Done';
  if (s === 'error') return 'Error';
  return stage;
}

function updateRebuildProgressUI(progress, rebuildRunning) {
  const status = document.getElementById('rebuild-progress-status');
  const bar = document.getElementById('rebuild-progress-bar');
  const meta = document.getElementById('rebuild-progress-meta');
  if (!status && !bar && !meta) return;

  const p = progress || {};
  const stageText = _formatStage(p.stage);
  const total = Number.isFinite(Number(p.total)) ? Number(p.total) : 0;
  const done = Number.isFinite(Number(p.done)) ? Number(p.done) : 0;
  const documents = Number.isFinite(Number(p.documents)) ? Number(p.documents) : 0;
  const chunks = Number.isFinite(Number(p.chunks)) ? Number(p.chunks) : 0;

  const pct = total > 0 ? Math.max(0, Math.min(100, Math.round((done / total) * 100))) : 0;
  if (bar) bar.style.width = total > 0 ? `${pct}%` : (rebuildRunning ? '4%' : '0%');

  const msg = (p.message || '').toString().trim();
  const err = (p.error || '').toString().trim();
  const summary = [];
  if (documents) summary.push(`${documents} docs`);
  if (chunks) summary.push(`${chunks} chunks`);
  if (total) summary.push(`${done}/${total} (${pct}%)`);

  if (status) {
    let line = stageText;
    if (summary.length) line += ` · ${summary.join(' · ')}`;
    if (msg) line += ` · ${msg}`;
    if (err) line += ` · ${err}`;
    status.innerText = line;
  }
  if (meta) {
    if (rebuildRunning) {
      meta.innerText = 'Live progress is streamed; no status polling loop needed.';
    } else {
      meta.innerText = '';
    }
  }
}

function updateStatusUI(data) {
  const mode = document.getElementById('mode');
  if (mode) mode.innerText = data.mode || '-';
  const embedding = document.getElementById('embedding');
  if (embedding) embedding.innerText = data.embedding || '-';
  const reranker = document.getElementById('reranker');
  if (reranker) reranker.innerText = data.reranker || '-';
  const docsCount = document.getElementById('docs-count');
  if (docsCount) docsCount.innerText = data.docs_count ?? '-';
  const needsRebuild = document.getElementById('needs-rebuild');
  if (needsRebuild) {
    const wasHidden = needsRebuild.style.display === 'none';
    needsRebuild.style.display = data.needs_rebuild ? 'block' : 'none';
    if (data.needs_rebuild && wasHidden) needsRebuild.classList.add('reveal');
  }
  const list = document.getElementById('sample-urls');
  if (list) {
    _clearChildren(list);
    if ((data.sample_urls || []).length === 0) {
      const li = document.createElement('li');
      li.style.cssText = 'color: var(--text-quaternary); font-style: italic;';
      li.textContent = 'No registered URLs';
      list.appendChild(li);
    } else {
      (data.sample_urls || []).forEach((u) => {
        const li = document.createElement('li');
        li.style.cssText = 'display: flex; align-items: start; gap: 8px; word-break: break-all;';
        const arrow = document.createElement('span');
        arrow.style.cssText = 'color: var(--text-tertiary); flex-shrink: 0;';
        arrow.textContent = '→';
        const text = document.createElement('span');
        text.style.cssText = 'flex: 1;';
        text.textContent = (u ?? '').toString();
        li.appendChild(arrow);
        li.appendChild(text);
        list.appendChild(li);
      });
    }
  }
  const rebuildFlag = document.getElementById('rebuild-flag');
  if (rebuildFlag) {
    rebuildFlag.classList.toggle('hidden', !data.rebuild_running);
    if (data.rebuild_running) rebuildFlag.classList.add('pulse'); else rebuildFlag.classList.remove('pulse');
  }
  const restartFlag = document.getElementById('restart-flag');
  if (restartFlag) {
    restartFlag.classList.toggle('hidden', !data.restart_required);
    if (data.restart_required) restartFlag.classList.add('pulse'); else restartFlag.classList.remove('pulse');
  }
}

export async function refreshStatus() {
  const data = await getStatus();
  updateStatusUI(data);
  updateRebuildProgressUI(data.rebuild_progress, data.rebuild_running);
  if (state.statusAuto.active && !data.rebuild_running) {
    setStatusAutoRefresh(false);
    if (!state.statusAuto.notifiedDone) {
      showToast('Index finished', 'success');
      state.statusAuto.notifiedDone = true;
    }
  }
}

export async function refreshDocs() {
  const data = await getDocs();
  const tbody = document.getElementById('docs-table');
  if (!tbody) return;
  _clearChildren(tbody);
  if ((data.docs || []).length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 4;
    td.style.cssText = 'text-align: center; padding: 48px 24px; color: var(--text-tertiary);';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('style', 'width: 48px; height: 48px; margin: 0 auto 12px; opacity: 0.4;');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('stroke', 'currentColor');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    path.setAttribute('d', 'M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z');
    svg.appendChild(path);
    const title = document.createElement('div');
    title.style.cssText = 'font-size: 13px;';
    title.textContent = 'No documents indexed yet';
    const subtitle = document.createElement('div');
    subtitle.style.cssText = 'font-size: 11px; margin-top: 4px; opacity: 0.7;';
    subtitle.textContent = 'Use the Ingest tab to add documents';
    td.appendChild(svg);
    td.appendChild(title);
    td.appendChild(subtitle);
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  data.docs.forEach((doc) => {
    const tr = document.createElement('tr');
    const tdId = document.createElement('td');
    tdId.style.cssText = "font-family: 'SF Mono', Monaco, monospace; font-size: 11px; color: var(--text-secondary);";
    tdId.textContent = (doc?.doc_id ?? '-').toString();
    const tdTitle = document.createElement('td');
    tdTitle.style.cssText = 'color: var(--text-primary);';
    tdTitle.textContent = (doc?.title ?? '-').toString() || '-';
    const tdUrl = document.createElement('td');
    tdUrl.style.cssText = 'font-size: 12px; color: var(--text-tertiary); max-width: 400px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
    tdUrl.textContent = (doc?.url ?? '-').toString() || '-';
    const tdCreated = document.createElement('td');
    tdCreated.style.cssText = 'font-size: 12px; color: var(--text-quaternary);';
    tdCreated.textContent = (doc?.created_at ?? '-').toString() || '-';
    tr.appendChild(tdId);
    tr.appendChild(tdTitle);
    tr.appendChild(tdUrl);
    tr.appendChild(tdCreated);
    tbody.appendChild(tr);
  });
}

export async function refreshFiles() {
  const data = await getUrlFiles();
  const fills = ['file-select', 'file-select-ingest'];
  fills.forEach((id) => {
    const select = document.getElementById(id);
    if (!select) return;
    _clearChildren(select);
    (data.files || []).forEach((f) => {
      const opt = document.createElement('option');
      opt.value = f; opt.text = f; select.appendChild(opt);
    });
  });
}

export function setStatusAutoRefresh(enable) {
  const st = state.statusAuto;
  if (enable) {
    if (st.active && st.id) return;
    st.active = true; st.notifiedDone = false;
    try {
      st.id = setInterval(() => { refreshStatus().catch(() => {}); }, 10000);
    } catch (_) {
      st.id = null; st.active = false;
    }
  } else {
    if (st.id) {
      try { clearInterval(st.id); } catch (_) { /* ignore */ }
      st.id = null;
    }
    st.active = false;
  }
}

export function startRebuildMonitoring() {
  try {
    if (rebuildEventSource) {
      try { rebuildEventSource.close(); } catch (_) { /* ignore */ }
      rebuildEventSource = null;
    }
    if (typeof EventSource === 'undefined') {
      setStatusAutoRefresh(true);
      return;
    }
    rebuildEventSource = new EventSource('/ui/api/rebuild/events');
    rebuildEventSource.onmessage = (ev) => {
      try {
        const payload = JSON.parse(ev.data || '{}');
        updateRebuildProgressUI(payload.progress, payload.rebuild_running);
        const rebuildFlag = document.getElementById('rebuild-flag');
        if (rebuildFlag) {
          rebuildFlag.classList.toggle('hidden', !payload.rebuild_running);
          if (payload.rebuild_running) rebuildFlag.classList.add('pulse'); else rebuildFlag.classList.remove('pulse');
        }
        const stage = (payload.progress?.stage || '').toString().toLowerCase();
        if (!payload.rebuild_running && (stage === 'done' || stage === 'error')) {
          stopRebuildMonitoring();
          if (stage === 'done') showToast('Index finished', 'success');
          if (stage === 'error') showToast('Index failed', 'error');
          refreshStatus().catch(() => {});
          refreshDocs().catch(() => {});
        }
      } catch (_) { /* ignore */ }
    };
    rebuildEventSource.onerror = () => {
      // Fallback: if SSE fails (proxy, browser), fall back to a slower poll.
      stopRebuildMonitoring();
      setStatusAutoRefresh(true);
    };
  } catch (_) {
    setStatusAutoRefresh(true);
  }
}

export function stopRebuildMonitoring() {
  if (rebuildEventSource) {
    try { rebuildEventSource.close(); } catch (_) { /* ignore */ }
    rebuildEventSource = null;
  }
  setStatusAutoRefresh(false);
}

function _resolveButton(elOrEvent) {
  if (!elOrEvent) return undefined;
  // If a DOM element was passed (e.g., inline onclick using `this`)
  if (elOrEvent.tagName) return elOrEvent.closest('button') || elOrEvent;
  // If an Event was passed
  const t = elOrEvent.target;
  if (t && t.closest) return t.closest('button') || t;
  return undefined;
}

export async function rebuildSitemap(elOrEvent) {
  const urlInput = document.getElementById('sitemap-url');
  const url = urlInput?.value?.trim() || '';
  if (!url) { showToast('You must specify a sitemap URL', 'error'); log('You must specify a sitemap'); return; }
  if (!isValidUrl(url)) { showToast('Invalid URL format', 'error'); log('Invalid URL format'); return; }
  const btn = _resolveButton(elOrEvent);
  setButtonLoading(btn, true);
  showToast('Indexing started. Live progress will stream…', 'success');
  startRebuildMonitoring();
  try {
    const data = await apiRebuildSitemap(url);
    log(`Rebuilt: docs=${data.documents} chunks=${data.chunks}`);
    showToast(`Rebuilt successfully: ${data.documents} docs, ${data.chunks} chunks`, 'success');
    stopRebuildMonitoring(); state.statusAuto.notifiedDone = true;
    showIngestSummaryModal(data.documents, data.chunks);
    refreshStatus();
    refreshDocs();
  } catch (e) {
    log('Error rebuilding sitemap: ' + e.message);
    showToast('Error rebuilding sitemap', 'error');
    stopRebuildMonitoring();
  } finally {
    setButtonLoading(btn, false);
  }
}

export async function rebuildFile(elOrEvent) {
  const select = document.getElementById('file-select-ingest') || document.getElementById('file-select');
  const file = select?.value || '';
  if (!file) { showToast('Please select a file', 'error'); log('Select a file'); return; }
  const btn = _resolveButton(elOrEvent);
  setButtonLoading(btn, true);
  showToast('Indexing started. Live progress will stream…', 'success');
  startRebuildMonitoring();
  try {
    const data = await apiRebuildFile(file);
    log(`Rebuilt: docs=${data.documents} chunks=${data.chunks}`);
    showToast(`Rebuilt successfully: ${data.documents} docs, ${data.chunks} chunks`, 'success');
    stopRebuildMonitoring(); state.statusAuto.notifiedDone = true;
    showIngestSummaryModal(data.documents, data.chunks);
    refreshStatus();
    refreshDocs();
  } catch (e) {
    log('Error rebuilding file: ' + e.message);
    showToast('Error rebuilding from file', 'error');
    stopRebuildMonitoring();
  } finally {
    setButtonLoading(btn, false);
  }
}

export function showIngestSummaryModal(documents, chunks) {
  try {
    const m = document.getElementById('ingest-modal');
    if (!m) return;
    const d = document.getElementById('ingest-documents-count');
    const c = document.getElementById('ingest-chunks-count');
    if (d) d.innerText = String(documents ?? 0);
    if (c) c.innerText = String(chunks ?? 0);
    m.classList.remove('hidden');
  } catch (_) { /* ignore */ }
}

export function hideIngestSummaryModal() {
  try { const m = document.getElementById('ingest-modal'); if (m) m.classList.add('hidden'); } catch (_) { /* ignore */ }
}

export function gotoRagDocs() {
  try {
    const ragTab = document.querySelector('.tab-btn[data-tab="rag"]');
    if (ragTab) ragTab.click();
    const docsBtn = document.querySelector('#tab-rag .tab-btn[data-subtab="rag-docs"]');
    if (docsBtn) docsBtn.click();
    setTimeout(() => { try { refreshDocs(); } catch (_) {} }, 50);
  } catch (_) { /* ignore */ }
}

export function registerGlobals() {
  window.refreshStatus = refreshStatus;
  window.refreshDocs = refreshDocs;
  window.refreshFiles = refreshFiles;
  window.rebuildSitemap = rebuildSitemap;
  window.rebuildFile = rebuildFile;
  window.setStatusAutoRefresh = setStatusAutoRefresh;
  window.startRebuildMonitoring = startRebuildMonitoring;
  window.stopRebuildMonitoring = stopRebuildMonitoring;
  window.showIngestSummaryModal = showIngestSummaryModal;
  window.hideIngestSummaryModal = hideIngestSummaryModal;
  window.gotoRagDocs = gotoRagDocs;
}

export async function init() {
  await refreshStatus();
  await refreshFiles();
  await refreshDocs();
}

export function onShow() {
  refreshStatus();
}
