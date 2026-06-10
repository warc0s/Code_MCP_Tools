import { getStatus, getGuidelines } from '../core/api.js';
import { log } from '../core/logger.js';
import { showToast } from '../core/toast.js';

let baseGuidelines = '';

function _clearChildren(el) {
  if (!el) return;
  while (el.firstChild) el.removeChild(el.firstChild);
}

function buildCodexSnippet(url) {
  const safeUrl = url || 'http://127.0.0.1:8000/mcp';
  return [
    'rmcp_client = true',
    '',
    '[mcp_servers.contextarium_local]',
    `url = "${safeUrl}"`,
    'startup_timeout_sec = 2',
    'tool_timeout_sec = 60',
    '',
  ].join('\n');
}

function buildClaudeAddCommand(url) {
  const safeUrl = url || 'http://127.0.0.1:8000/mcp';
  return `claude mcp add --transport http contextarium ${safeUrl}`;
}

function buildCopilotJson(url) {
  const safeUrl = url || 'http://127.0.0.1:8000/mcp';
  return [
    '{',
    '  "servers": {',
    '    "contextarium": {',
    '      "type": "http",',
    `      "url": "${safeUrl}"`,
    '    }',
    '  }',
    '}',
  ].join('\n');
}

export async function refreshDashboardStatus() {
  log('Updating dashboard status...');
  const data = await getStatus();
  const mode = document.getElementById('mode');
  if (mode) mode.innerText = data.mode || '-';
  const embedding = document.getElementById('embedding');
  if (embedding) embedding.innerText = data.embedding || '-';
  const reranker = document.getElementById('reranker');
  if (reranker) reranker.innerText = data.reranker || '-';
  const docsCount = document.getElementById('docs-count');
  if (docsCount) docsCount.innerText = data.docs_count ?? '-';
  const mcpPath = document.getElementById('mcp-path-dashboard');
  if (mcpPath) mcpPath.innerText = data.mcp_url || data.mcp_path || '/mcp';
  const sel = (data.selected_project || '').trim();
  const selEl = document.getElementById('selected-project'); if (selEl) selEl.innerText = sel || '-';
  const counts = data.items_counts || { memory: 0, doc: 0, bug: 0, todo: 0 };
  const total = (counts.memory || 0) + (counts.doc || 0) + (counts.bug || 0) + (counts.todo || 0);
  const totEl = document.getElementById('items-total'); if (totEl) totEl.innerText = String(total);
  const byTypeEl = document.getElementById('items-by-type'); if (byTypeEl) byTypeEl.innerText = `memory: ${counts.memory || 0} · docs: ${counts.doc || 0} · bugs: ${counts.bug || 0} · todos: ${counts.todo || 0}`;
  const tools = Array.isArray(data.runtime_tools) ? data.runtime_tools : [];
  const groupMap = data.tool_groups || {};
  const enabled = new Set(tools);
  const grouped = [];
  const seen = new Set();
  Object.keys(groupMap).forEach((group) => {
    const names = (groupMap[group] || []).filter((n) => enabled.has(n));
    names.forEach((n) => seen.add(n));
    if (names.length > 0) grouped.push({ group, names });
  });
  const others = tools.filter((n) => !seen.has(n));
  if (others.length > 0) grouped.push({ group: 'other', names: others });
  const container = document.getElementById('runtime-tools-grouped');
  if (container) {
    _clearChildren(container);
    if (grouped.length === 0) {
      const p = document.createElement('div');
      p.style.cssText = 'font-size:12px; color: var(--text-quaternary); font-style: italic;';
      p.textContent = 'No tools enabled';
      container.appendChild(p);
    } else {
      grouped.forEach(({ group, names }) => {
        const block = document.createElement('div');
        const nice = (group || '').replace(/_/g, ' ').replace(/\b[a-z]/g, (m) => m.toUpperCase());
        const header = document.createElement('div');
        header.style.cssText = 'font-size:11px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing:0.05em; margin-bottom:6px;';
        header.textContent = nice;
        const list = document.createElement('div');
        list.style.cssText = 'display:flex; flex-wrap: wrap; gap:6px;';
        names.forEach((n) => {
          const tag = document.createElement('span');
          tag.style.cssText = 'padding:2px 8px; border:1px solid var(--border-secondary); border-radius:999px; font-size:12px; color: var(--text-secondary);';
          tag.textContent = n;
          list.appendChild(tag);
        });
        block.appendChild(header);
        block.appendChild(list);
        container.appendChild(block);
      });
    }
  }
  const needsRebuild = document.getElementById('needs-rebuild-dashboard');
  if (needsRebuild) {
    const wasHidden = needsRebuild.classList.contains('hidden');
    if (data.needs_rebuild) {
      needsRebuild.classList.remove('hidden');
      if (wasHidden) needsRebuild.classList.add('reveal');
    } else {
      needsRebuild.classList.add('hidden');
    }
  }
  const list = document.getElementById('sample-urls-dashboard');
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
  const restartFlag = document.getElementById('restart-flag');
  if (restartFlag) {
    restartFlag.classList.toggle('hidden', !data.restart_required);
    if (data.restart_required) restartFlag.classList.add('pulse'); else restartFlag.classList.remove('pulse');
  }
  const statusPill = document.getElementById('status-pill');
  if (statusPill) {
    _clearChildren(statusPill);
    const dot = document.createElement('span');
    dot.className = 'pulse';
    dot.style.cssText = 'width: 6px; height: 6px; border-radius: 50%;';
    if (data.db_exists) {
      dot.style.background = '#22c55e';
      statusPill.appendChild(dot);
      statusPill.appendChild(document.createTextNode('MCP Ready'));
      statusPill.style.cssText = 'background: rgba(34, 197, 94, 0.15); color: #16a34a; border: 1px solid rgba(34, 197, 94, 0.3); font-weight: 500;';
    } else {
      dot.style.background = '#ef4444';
      statusPill.appendChild(dot);
      statusPill.appendChild(document.createTextNode('MCP Not Ready'));
      statusPill.style.cssText = 'background: rgba(239, 68, 68, 0.15); color: #dc2626; border: 1px solid rgba(239, 68, 68, 0.3); font-weight: 500;';
    }
  }
}

export async function loadGuidelines() {
  try {
    const content = await getGuidelines();
    baseGuidelines = content || '';
    const textarea = document.getElementById('guidelines-content');
    if (textarea) {
      textarea.value = baseGuidelines;
      textarea.scrollTop = 0;
    }
  } catch (e) {
    log('Error loading guidelines: ' + e.message);
    const textarea = document.getElementById('guidelines-content');
    if (textarea) textarea.value = 'Error loading guidelines. Please check the console.';
  }
}

export async function refreshIntegrations() {
  const data = await getStatus();
  const url = data.mcp_url || data.mcp_path || '/mcp';
  const code = buildCodexSnippet(url);
  const ta = document.getElementById('codex-config-snippet');
  if (ta) ta.value = code;
  const gcur = document.getElementById('integrations-current-url'); if (gcur) gcur.textContent = url;
  const claudeTa = document.getElementById('claude-add-cmd'); if (claudeTa) claudeTa.value = buildClaudeAddCommand(url);
  const cop = document.getElementById('copilot-mcp-json'); if (cop) cop.value = buildCopilotJson(url);
}

export function copyGuidelines() {
  const content = document.getElementById('guidelines-content')?.value || '';
  navigator.clipboard.writeText(content).then(() => showToast('Guidelines copied to clipboard', 'success')).catch(() => showToast('Failed to copy guidelines', 'error'));
}

export function copyCodexCommand() {
  navigator.clipboard.writeText('nano ~/.codex/config.toml').then(() => showToast('Command copied', 'success')).catch(() => showToast('Failed to copy', 'error'));
}

export function copyCodexConfig() {
  const ta = document.getElementById('codex-config-snippet');
  navigator.clipboard.writeText(ta?.value || '').then(() => showToast('Config snippet copied', 'success')).catch(() => showToast('Failed to copy config', 'error'));
}

export function copyClaudeCommand() {
  const ta = document.getElementById('claude-add-cmd');
  const text = (ta && ta.value) ? ta.value : buildClaudeAddCommand('http://127.0.0.1:8000/mcp');
  navigator.clipboard.writeText(text).then(() => showToast('Command copied', 'success')).catch(() => showToast('Failed to copy', 'error'));
}

export function copyClaudeVerify() {
  navigator.clipboard.writeText('claude mcp list').then(() => showToast('Command copied', 'success')).catch(() => showToast('Failed to copy', 'error'));
}

export function copyIntegrationsUrl() {
  const el = document.getElementById('integrations-current-url');
  const text = el && el.textContent ? el.textContent.trim() : '';
  if (!text) {
    showToast('No URL to copy', 'error');
    return;
  }
  navigator.clipboard.writeText(text).then(() => showToast('URL copied', 'success')).catch(() => showToast('Failed to copy URL', 'error'));
}

export function copyCopilotJson() {
  const ta = document.getElementById('copilot-mcp-json');
  navigator.clipboard.writeText(ta?.value || '').then(() => showToast('JSON copied', 'success')).catch(() => showToast('Failed to copy JSON', 'error'));
}

export function registerGlobals() {
  window.refreshDashboardStatus = refreshDashboardStatus;
  window.loadGuidelines = loadGuidelines;
  window.refreshIntegrations = refreshIntegrations;
  window.copyGuidelines = copyGuidelines;
  window.copyCodexCommand = copyCodexCommand;
  window.copyCodexConfig = copyCodexConfig;
  window.copyClaudeCommand = copyClaudeCommand;
  window.copyClaudeVerify = copyClaudeVerify;
  window.copyIntegrationsUrl = copyIntegrationsUrl;
  window.copyCopilotJson = copyCopilotJson;
}

export async function init() {
  await refreshDashboardStatus();
  await loadGuidelines();
  await refreshIntegrations();
}

export function onShow() {
  refreshDashboardStatus();
}
