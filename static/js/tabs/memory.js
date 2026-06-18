import { boardStatuses, getCurrentProject, setCurrentProject, setCurrentItemType, getCurrentItemType } from '../core/state.js';
import { parseJsonSafe, parseTags, escapeHtml, isValidUrl } from '../core/utils.js';
import { createItem as apiCreateItem, listItems, updateItem, replaceItemBody, deleteItem as apiDeleteItem } from '../core/api.js';
import { showToast } from '../core/toast.js';
import { log } from '../core/logger.js';

function getMetaTemplate(type) {
  switch ((type || '').toLowerCase()) {
    case 'bug':
      return JSON.stringify({
        logs_excerpt: 'copy here the most relevant log lines',
        done_summary: 'what was implemented/fixed and why (>= 120 chars)',
        resolution_criteria: [
          'criterion 1 (e.g., tests green)',
          'criterion 2 (e.g., no errors in console)',
        ],
        screenshots: [],
        related_files: [],
      }, null, 2);
    case 'todo':
      return JSON.stringify({
        reproduction: 'optional, only for bug-like tasks',
        dependencies: [],
        related_files: [],
        done_summary: 'what was implemented and why (>= 120 chars)',
      }, null, 2);
    case 'doc':
      return JSON.stringify({
        source_url: '',
        version_notes: 'what changed and when',
      }, null, 2);
    case 'memory':
    default:
      return JSON.stringify({
        related_links: [],
      }, null, 2);
  }
}

function getMetaHelp(type) {
  switch ((type || '').toLowerCase()) {
    case 'bug':
      return 'Extras in meta: logs_excerpt, done_summary (>= 120 chars when resolving), resolution_criteria (list), screenshots (URLs, optional), related_files (list). Required fields are in the typed section.';
    case 'todo':
      return 'Extras in meta: reproduction (optional), dependencies (list), related_files (list), done_summary (>= 120 chars when resolving). Required fields are in the typed section.';
    case 'doc':
      return 'Extras in meta: source_url, version_notes. Authors/related_docs are typed fields.';
    case 'memory':
    default:
      return 'Extras in meta: related_links. Required fields are in the typed section.';
  }
}

function updateMetaGuidance() {
  const help = document.getElementById('meta-help-text');
  if (help) help.innerText = getMetaHelp(getCurrentItemType());
  const metaEl = document.getElementById('item-meta');
  if (metaEl) {
    // Auto-apply template on type change, to avoid stale meta from previous type
    metaEl.value = getMetaTemplate(getCurrentItemType());
  }
  // Render typed fields for the current type in the create form
  try { renderTypedFieldsInCreate(); } catch (_) {}
}

export function applyMetaTemplate() {
  const metaEl = document.getElementById('item-meta');
  if (!metaEl) return;
  metaEl.value = getMetaTemplate(getCurrentItemType());
  showToast('Template inserted. Adjust as needed.', 'success');
}

function populateStatusSelects() {
  const statusOptions = ['<option value="">(none)</option>', ...boardStatuses.map((s) => `<option value="${s.key}">${s.label}</option>`)].join('');
  const createStatus = document.getElementById('item-status');
  const editStatus = document.getElementById('edit-status');
  if (createStatus) createStatus.innerHTML = statusOptions;
  if (editStatus) editStatus.innerHTML = statusOptions;
}

export function setMemoryType(type) {
  setCurrentItemType(type);
  document.querySelectorAll('button[data-memtype]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.memtype === type);
  });
  const typeSelect = document.getElementById('item-type');
  if (typeSelect) typeSelect.value = type;
  updateMetaGuidance();
  refreshItems();
}

export async function createItem() {
  const project = getCurrentProject();
  const type = getCurrentItemType();
  const title = document.getElementById('item-title')?.value || '';
  const status = document.getElementById('item-status')?.value || '';
  const tags = parseTags(document.getElementById('item-tags')?.value || '');
  const typed = collectTypedFromCreate(type);
  const meta = parseJsonSafe(document.getElementById('item-meta')?.value, {});
  const body_md = document.getElementById('item-body')?.value || '';
  if (!project.trim()) { showToast('Select a project in Settings', 'error'); return; }
  log('Creating item...');
  try {
    await apiCreateItem({ project, type, title, body_md, tags, status, meta, typed });
    showToast('Item created', 'success');
    setCurrentProject(project || getCurrentProject());
    refreshItems();
  } catch (e) {
    log('Create item failed: ' + e.message);
    showToast(e.message || 'Failed to create item', 'error');
  }
}

export async function refreshItems() {
  const project = getCurrentProject();
  if (!project.trim()) {
    showToast('Select a project in Settings', 'error');
    return;
  }
  const params = { project: project.trim(), item_type: getCurrentItemType(), limit: '200' };
  log('Fetching items...');
  try {
    const data = await listItems(params);
    renderItems(data.items || []);
  } catch (e) {
    log('Fetch items failed: ' + e.message);
    showToast(e.message || 'Failed to fetch items', 'error');
  }
}

export function clearItems() {
  const container = document.getElementById('board');
  if (container) container.innerHTML = '';
  const list = document.getElementById('list');
  if (list) list.innerHTML = '';
}

function renderItems(items) {
  const board = document.getElementById('board');
  const list = document.getElementById('list');
  if (!board || !list) return;
  const t = getCurrentItemType();
  if (t === 'todo' || t === 'bug') {
    board.style.display = 'grid';
    list.style.display = 'none';
    const statuses = getBoardStatusesForType(t);
    renderBoard(items, statuses);
  } else {
    board.style.display = 'none';
    list.style.display = 'grid';
    renderList(items);
  }
}

// Cache last fetched items for quick lookups
const itemsCache = new Map();

function renderList(items) {
  const list = document.getElementById('list');
  if (!list) return;
  list.innerHTML = '';
  (items || []).forEach((item) => {
    itemsCache.set(item.id, item);
    const card = document.createElement('div');
    card.style.cssText = 'background: var(--bg-secondary); border: 1px solid var(--border-hover); border-radius: 6px; padding: 12px; box-shadow: var(--shadow);';
    const header = document.createElement('div');
    header.style.cssText = 'display:flex; align-items:center; justify-content: space-between; gap:8px; margin-bottom:6px;';
    const left = document.createElement('div');
    left.innerHTML = `<div style="font-weight:600; color: var(--text-primary);">${escapeHtml(item.title || '(untitled)')}</div><div style="font-size:11px; color: var(--text-tertiary);">${item.type || ''} - v${item.version || ''}</div>`;
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex; gap:6px;';
    const showBtn = document.createElement('button');
    showBtn.className = 'ghost-btn';
    showBtn.style.cssText = 'padding:6px 8px;';
    showBtn.innerText = 'Show';
    showBtn.title = 'Show details';
    showBtn.addEventListener('click', () => openItemModal(item));
    const editBtn = document.createElement('button');
    editBtn.className = 'ghost-btn';
    editBtn.style.cssText = 'padding:6px 8px;';
    editBtn.textContent = 'Edit';
    editBtn.title = 'Edit item';
    editBtn.addEventListener('click', () => toggleInlineEdit(card, item));
    const delBtn = document.createElement('button');
    delBtn.className = 'ghost-btn';
    delBtn.style.cssText = 'padding:6px 8px; color:#ef4444; border-color: rgba(239,68,68,0.4);';
    delBtn.innerText = 'Delete';
    delBtn.addEventListener('click', () => deleteItem(item.id));
    actions.appendChild(showBtn);
    actions.appendChild(editBtn);
    actions.appendChild(delBtn);
    header.appendChild(left);
    header.appendChild(actions);
    const metaLine = document.createElement('div');
    metaLine.style.cssText = 'font-size:12px; color: var(--text-tertiary);';
    metaLine.innerText = `tags: ${(item.tags || []).join(', ') || '-'}`;
    const bodyLine = document.createElement('div');
    bodyLine.style.cssText = 'font-size:12px; color: var(--text-secondary); margin-top:6px; max-height: 80px; overflow: hidden;';
    bodyLine.innerText = (item.body_md || '').slice(0, 240);
    const editor = document.createElement('div');
    editor.className = 'inline-editor';
    editor.style.cssText = 'display:none; border-top:1px dashed var(--border-secondary); margin-top:8px; padding-top:8px;';
    card.appendChild(header);
    card.appendChild(metaLine);
    card.appendChild(bodyLine);
    card.appendChild(editor);
    list.appendChild(card);
  });
}

function renderTypedFieldsInCreate() {
  const container = document.getElementById('typed-fields');
  if (!container) return;
  const type = getCurrentItemType();
  container.innerHTML = buildTypedFieldsHtml(type, null);
}

function buildTypedFieldsHtml(type, data) {
  const t = (type || '').toLowerCase();
  const val = (k, def='') => (data && data[k] != null ? data[k] : def);
  if (t === 'bug') {
    return `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap:8px;">
        <div>
          <label class="label">Severity</label>
          <select class="input ${data ? 'ie-bug-severity' : 'tf-bug-severity'}">
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </div>
        <div>
          <label class="label">Expected</label>
          <input class="input ${data ? 'ie-bug-expected' : 'tf-bug-expected'}" value="${escapeHtml(val('expected'))}" />
        </div>
      </div>
      <div style="margin-top:8px;">
        <label class="label">Reproduction</label>
        <textarea class="input ${data ? 'ie-bug-reproduction' : 'tf-bug-reproduction'}" style="height:70px;">${escapeHtml(val('reproduction'))}</textarea>
      </div>
      <div style="margin-top:8px;">
        <label class="label">Root cause</label>
        <textarea class="input ${data ? 'ie-bug-root' : 'tf-bug-root'}" style="height:70px;">${escapeHtml(val('root_cause'))}</textarea>
      </div>
    `;
  }
  if (t === 'todo') {
    return `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap:8px;">
        <div>
          <label class="label">Kind</label>
          <select class="input ${data ? 'ie-todo-kind' : 'tf-todo-kind'}">
            <option value="feature">feature</option>
            <option value="bug_fix">bug_fix</option>
            <option value="refactor">refactor</option>
            <option value="chore">chore</option>
          </select>
        </div>
        <div>
          <label class="label">Priority</label>
          <select class="input ${data ? 'ie-todo-priority' : 'tf-todo-priority'}">
            <option value="p2">p2</option>
            <option value="p1">p1</option>
            <option value="p0">p0</option>
          </select>
        </div>
      </div>
      <div style="font-size:12px; color: var(--text-tertiary); margin-top:4px;">Priority levels: p0 (highest/urgent), p1 (high), p2 (normal)</div>
      <div style="margin-top:8px;">
        <label class="label">Acceptance criteria (comma-separated)</label>
        <input class="input ${data ? 'ie-todo-criteria' : 'tf-todo-criteria'}" value="${escapeHtml(((val('acceptance_criteria', []) || [])).join(', '))}" />
      </div>
    `;
  }
  if (t === 'memory') {
    return `
      <div style="display:grid; grid-template-columns: 1fr; gap:8px;">
        <div><label class="label">Topic</label><input class="input ${data ? 'ie-mem-topic' : 'tf-mem-topic'}" value="${escapeHtml(val('topic'))}" /></div>
        <div><label class="label">Decision</label><input class="input ${data ? 'ie-mem-decision' : 'tf-mem-decision'}" value="${escapeHtml(val('decision'))}" /></div>
        <div><label class="label">Context</label><textarea class="input ${data ? 'ie-mem-context' : 'tf-mem-context'}" style="height:70px;">${escapeHtml(val('context'))}</textarea></div>
        <div><label class="label">Rationale</label><textarea class="input ${data ? 'ie-mem-rationale' : 'tf-mem-rationale'}" style="height:70px;">${escapeHtml(val('rationale'))}</textarea></div>
      </div>
    `;
  }
  if (t === 'doc') {
    return `
      <div style="display:grid; grid-template-columns: 1fr; gap:8px;">
        <div><label class="label">Authors (comma-separated)</label><input class="input ${data ? 'ie-doc-authors' : 'tf-doc-authors'}" value="${escapeHtml(((val('authors', []) || [])).join(', '))}" /></div>
        <div><label class="label">Related docs (comma-separated)</label><input class="input ${data ? 'ie-doc-related' : 'tf-doc-related'}" value="${escapeHtml(((val('related_docs', []) || [])).join(', '))}" /></div>
      </div>
    `;
  }
  return '';
}

function collectTypedFromCreate(type) {
  const t = (type || '').toLowerCase();
  if (t === 'bug') {
    const sev = document.querySelector('.tf-bug-severity')?.value || 'medium';
    const exp = document.querySelector('.tf-bug-expected')?.value || '';
    const rep = document.querySelector('.tf-bug-reproduction')?.value || '';
    const rc = document.querySelector('.tf-bug-root')?.value || '';
    return { severity: sev, expected: exp, reproduction: rep, root_cause: rc };
  }
  if (t === 'todo') {
    const kind = document.querySelector('.tf-todo-kind')?.value || 'feature';
    const pr = document.querySelector('.tf-todo-priority')?.value || 'p2';
    const crit = (document.querySelector('.tf-todo-criteria')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
    return { kind, priority: pr, acceptance_criteria: crit };
  }
  if (t === 'memory') {
    const topic = document.querySelector('.tf-mem-topic')?.value || '';
    const decision = document.querySelector('.tf-mem-decision')?.value || '';
    const context = document.querySelector('.tf-mem-context')?.value || '';
    const rationale = document.querySelector('.tf-mem-rationale')?.value || '';
    return { topic, decision, context, rationale };
  }
  if (t === 'doc') {
    const authors = (document.querySelector('.tf-doc-authors')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
    const related = (document.querySelector('.tf-doc-related')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
    return { authors, related_docs: related };
  }
  return null;
}

function collectTypedFromEditor(editorEl, type) {
  const t = (type || '').toLowerCase();
  if (t === 'bug') {
    const sev = editorEl.querySelector('.ie-bug-severity')?.value;
    const exp = editorEl.querySelector('.ie-bug-expected')?.value;
    const rep = editorEl.querySelector('.ie-bug-reproduction')?.value;
    const rc = editorEl.querySelector('.ie-bug-root')?.value;
    const out = {};
    if (sev) out.severity = sev;
    if (exp) out.expected = exp;
    if (rep) out.reproduction = rep;
    if (rc) out.root_cause = rc;
    return out;
  }
  if (t === 'todo') {
    const kind = editorEl.querySelector('.ie-todo-kind')?.value;
    const pr = editorEl.querySelector('.ie-todo-priority')?.value;
    const crit = (editorEl.querySelector('.ie-todo-criteria')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
    const out = {};
    if (kind) out.kind = kind;
    if (pr) out.priority = pr;
    if (editorEl.querySelector('.ie-todo-criteria')) out.acceptance_criteria = crit;
    return out;
  }
  if (t === 'memory') {
    const topic = editorEl.querySelector('.ie-mem-topic')?.value;
    const decision = editorEl.querySelector('.ie-mem-decision')?.value;
    const context = editorEl.querySelector('.ie-mem-context')?.value;
    const rationale = editorEl.querySelector('.ie-mem-rationale')?.value;
    const out = {};
    if (topic) out.topic = topic;
    if (decision) out.decision = decision;
    if (context) out.context = context;
    if (rationale) out.rationale = rationale;
    return out;
  }
  if (t === 'doc') {
    const authors = (editorEl.querySelector('.ie-doc-authors')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
    const related = (editorEl.querySelector('.ie-doc-related')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
    const out = {};
    if (editorEl.querySelector('.ie-doc-authors')) out.authors = authors;
    if (editorEl.querySelector('.ie-doc-related')) out.related_docs = related;
    return out;
  }
  return null;
}
function toggleInlineEdit(card, item) {
  const existing = card.querySelector('.inline-editor');
  if (!existing) return;
  if (existing.dataset.loaded !== '1') {
    const statusOptions = ['<option value="">(none)</option>', ...boardStatuses.map((s) => `<option value="${s.key}">${s.label}</option>`)];
    existing.innerHTML = `
      <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap:8px;">
        <div>
          <label class="label">Title</label>
          <input class="input ie-title" value="${escapeHtml(item.title || '')}" />
        </div>
        <div>
          <label class="label">Status</label>
          <select class="input ie-status">${statusOptions.join('')}</select>
        </div>
        <div>
          <label class="label">Tags</label>
          <input class="input ie-tags" value="${escapeHtml((item.tags || []).join(', '))}" />
        </div>
      </div>
      <div style="display:grid; grid-template-columns: 1fr; gap:8px; margin-top:8px;">
        <div style="display:flex; align-items:center; justify-content: space-between;">
          <label class="label">Meta (JSON)</label>
          <button class="ghost-btn ie-template" type="button" title="Insert a template for this type">Use template</button>
        </div>
        <textarea class="input ie-meta" style="height:100px;">${escapeHtml(JSON.stringify(item.meta || {}, null, 2))}</textarea>
        <div class="ie-meta-help" style="font-size: 12px; color: var(--text-tertiary);">${escapeHtml(getMetaHelp ? getMetaHelp(item.type) : '')}</div>
      </div>
      <div style="margin-top:8px;">
        <label class="label">Body (markdown)</label>
        <textarea class="input ie-body" style="height:140px;">${escapeHtml(item.body_md || '')}</textarea>
      </div>
      <div style="margin-top:8px;">
        <div class="ie-typed">${buildTypedFieldsHtml(item.type, item.typed || {})}</div>
      </div>
      <div style="display:flex; gap:8px; margin-top:8px;">
        <button class="primary-btn ie-save" style="flex:1;">Save</button>
        <button class="ghost-btn ie-cancel">Cancel</button>
      </div>
    `;
    const statusSel = existing.querySelector('.ie-status');
    if (statusSel) statusSel.value = item.status || '';
    const tplBtn = existing.querySelector('.ie-template');
    if (tplBtn) {
      tplBtn.addEventListener('click', () => {
        const area = existing.querySelector('.ie-meta');
        if (area) { area.value = getMetaTemplate(item.type); showToast('Template inserted. Adjust as needed.', 'success'); }
      });
    }
    existing.querySelector('.ie-save')?.addEventListener('click', async () => {
      await saveInlineEdit(existing, item);
    });
    existing.querySelector('.ie-cancel')?.addEventListener('click', () => {
      existing.style.display = 'none';
    });
    existing.dataset.loaded = '1';
  }
  existing.style.display = (existing.style.display === 'none' || !existing.style.display) ? 'block' : 'none';
}

async function saveInlineEdit(editorEl, item) {
  const project = getCurrentProject();
  if (!project) { showToast('Set a project first', 'error'); return; }
  const title = editorEl.querySelector('.ie-title')?.value || '';
  const status = editorEl.querySelector('.ie-status')?.value || '';
  const tags = (editorEl.querySelector('.ie-tags')?.value || '').split(',').map((s) => s.trim()).filter(Boolean);
  let meta = {};
  try { meta = JSON.parse(editorEl.querySelector('.ie-meta')?.value || '{}'); } catch (_) { showToast('Invalid meta JSON', 'error'); return; }
  const bodyEl = editorEl.querySelector('.ie-body');
  const newBody = bodyEl ? bodyEl.value : undefined;
  const fields = {};
  if (title) fields.title = title;
  if (status) fields.status = status;
  if (tags) fields.tags = tags;
  if (meta && typeof meta === 'object') fields.meta = meta;
  const typed = collectTypedFromEditor(editorEl, item.type);
  if (typed && Object.keys(typed).length > 0) fields.typed = typed;
  // UX: if resolving bug/todo without required meta, guide the user
  const t = (item.type || '').toLowerCase();
  if ((fields.status || item.status) === 'resolved' && (t === 'bug' || t === 'todo')) {
    let candidate = fields.meta || item.meta || {};
    if (!hasValidResolutionMeta(candidate)) {
      const data = await showResolveModal({ meta: candidate });
      if (!data) return; // user cancelled
      const merged = { ...(fields.meta || item.meta || {}), done_summary: data.done_summary, related_files: data.related_files };
      fields.meta = merged;
    }
  }
  try {
    if (Object.keys(fields).length > 0) {
      const res = await updateItem(project, item.id, fields);
      item = res.item || item;
    }
    if (typeof newBody === 'string' && newBody !== (item.body_md || '')) {
      await replaceItemBody(project, item.id, newBody, item.version);
    }
    showToast('Item saved', 'success');
    refreshItems();
  } catch (e) {
    log('Inline update failed: ' + e.message);
    showToast(e.message || 'Failed to update item', 'error');
  }
}

function getBoardStatusesForType(type) {
  const t = (type || '').toLowerCase();
  if (t === 'bug') return boardStatuses.filter((s) => s.key === 'pending' || s.key === 'resolved');
  return boardStatuses;
}

function getDisplayStatusKey(item, type) {
  const status = (item?.status || 'pending').toLowerCase();
  if ((type || '').toLowerCase() === 'bug' && status !== 'resolved') return 'pending';
  return status;
}

function renderBoard(items, statuses) {
  const board = document.getElementById('board');
  if (!board) return;
  board.innerHTML = '';
  const byStatus = {};
  const currentType = getCurrentItemType();
  items.forEach((item) => {
    itemsCache.set(item.id, item);
    const statusKey = getDisplayStatusKey(item, currentType);
    byStatus[statusKey] = byStatus[statusKey] || [];
    byStatus[statusKey].push(item);
  });

  (statuses || boardStatuses).forEach((status) => {
    const col = document.createElement('div');
    col.style.cssText = 'background: var(--bg-tertiary); border: 1px solid var(--border-secondary); border-radius: 8px; padding: 10px; min-height: 160px;';
    col.dataset.status = status.key;
    col.addEventListener('dragover', (e) => e.preventDefault());
    col.addEventListener('drop', (e) => handleDrop(e, status.key));

    const title = document.createElement('div');
    title.style.cssText = 'font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); margin-bottom: 6px;';
    title.innerText = status.label;
    col.appendChild(title);

    (byStatus[status.key] || []).forEach((item) => {
      const card = document.createElement('div');
      card.draggable = true;
      card.dataset.id = item.id;
      card.dataset.status = status.key;
      card.addEventListener('dragstart', (e) => handleDragStart(e, item.id));
      card.addEventListener('dragend', handleDragEnd);
      card.style.cssText = 'background: var(--bg-secondary); border: 1px solid var(--border-hover); border-radius: 6px; padding: 10px; margin-bottom: 8px; box-shadow: var(--shadow);';

      const safeTitle = escapeHtml(item.title || '(untitled)');
      const safeBody = escapeHtml((item.body_md || '').slice(0, 140));

      const header = document.createElement('div');
      header.style.cssText = 'display:flex; justify-content: space-between; gap:8px; align-items:center;';
      const hTitle = document.createElement('div');
      hTitle.style.cssText = 'font-weight:600; color: var(--text-primary);';
      hTitle.innerHTML = safeTitle;
      const hVer = document.createElement('div');
      hVer.style.cssText = 'font-size:11px; color: var(--text-tertiary);';
      hVer.innerText = 'v' + (item.version ? item.version : '');
      header.appendChild(hTitle);
      header.appendChild(hVer);

      const metaLine = document.createElement('div');
      metaLine.style.cssText = 'font-size:12px; color: var(--text-tertiary); margin:4px 0;';
      metaLine.innerText = `${item.type || ''} : ${item.id || ''}`;

      const tagsLine = document.createElement('div');
      tagsLine.style.cssText = 'font-size:12px; color: var(--text-tertiary);';
      const tagsText = (item.tags || []).join(', ') || '-';
      tagsLine.innerText = `tags: ${tagsText}`;

      const bodyLine = document.createElement('div');
      bodyLine.style.cssText = 'font-size:12px; color: var(--text-secondary); margin-top:4px; max-height: 60px; overflow: hidden;';
      bodyLine.innerHTML = safeBody;

      const actions = document.createElement('div');
      actions.style.cssText = 'margin-top:8px; display:flex; gap:6px; flex-wrap: wrap;';

      const showBtn = document.createElement('button');
      showBtn.className = 'ghost-btn';
      showBtn.style.cssText = 'padding:6px 8px;';
      showBtn.innerText = 'Show';
      showBtn.title = 'Show details';
      showBtn.addEventListener('click', () => openItemModal(item));

      const editBtn = document.createElement('button');
      editBtn.className = 'ghost-btn';
      editBtn.style.cssText = 'padding:6px 8px;';
      editBtn.textContent = 'Edit';
      editBtn.title = 'Edit item';
      editBtn.addEventListener('click', () => toggleInlineEdit(card, item));

      const delBtn = document.createElement('button');
      delBtn.className = 'ghost-btn';
      delBtn.style.cssText = 'padding:6px 8px; color:#ef4444; border-color: rgba(239,68,68,0.4);';
      delBtn.innerText = 'Delete';
      delBtn.addEventListener('click', () => deleteItem(item.id));

      actions.appendChild(showBtn);
      actions.appendChild(editBtn);
      actions.appendChild(delBtn);

      card.appendChild(header);
      card.appendChild(metaLine);
      card.appendChild(tagsLine);
      card.appendChild(bodyLine);
      card.appendChild(actions);
      const editor = document.createElement('div');
      editor.className = 'inline-editor';
      editor.style.cssText = 'display:none; border-top:1px dashed var(--border-secondary); margin-top:8px; padding-top:8px;';
      card.appendChild(editor);

      col.appendChild(card);
  });
  board.appendChild(col);
  });
}

function handleDragStart(event, id) {
  event.dataTransfer.setData('text/plain', id);
}

function handleDragEnd() { /* no-op */ }

async function handleDrop(event, status) {
  event.preventDefault();
  const id = event.dataTransfer.getData('text/plain');
  if (!id) return;
  await updateStatus(id, status);
}

function hasValidResolutionMeta(meta) {
  try {
    const ds = (meta && typeof meta === 'object' ? (meta.done_summary || '') : '').trim();
    const files = (meta && typeof meta === 'object' ? (meta.related_files || []) : []);
    const hasFiles = Array.isArray(files) && files.some((x) => String(x || '').trim().length > 0);
    return ds.length >= 120 && hasFiles;
  } catch (_) { return false; }
}

function showResolveModal(item) {
  return new Promise((resolve) => {
    const doneSummary = escapeHtml(item.meta?.done_summary || '');
    const relatedFiles = escapeHtml((item.meta?.related_files || []).join(', '));
    const overlay = document.createElement('div');
    overlay.style.cssText = 'position:fixed; inset:0; background:rgba(0,0,0,0.5); display:flex; align-items:center; justify-content:center; z-index:1000;';
    const box = document.createElement('div');
    box.style.cssText = 'background: var(--bg-primary); border:1px solid var(--border-secondary); border-radius:8px; width: 520px; max-width: 92vw; padding: 16px;';
    box.innerHTML = `
      <div style="font-size:14px; font-weight:700; color:var(--text-primary); margin-bottom:8px;">Complete resolution details</div>
      <div style="font-size:12px; color:var(--text-secondary); margin-bottom:8px;">When resolving, add a short summary and the files touched.</div>
      <div>
        <label class="label">Done summary (>= 120 chars)</label>
        <textarea id="rs-done" class="input" style="height:120px;">${doneSummary}</textarea>
      </div>
      <div style="margin-top:8px;">
        <label class="label">Related files (comma-separated)</label>
        <input id="rs-files" class="input" value="${relatedFiles}">
      </div>
      <div style="display:flex; gap:8px; margin-top:12px;">
        <button id="rs-ok" class="primary-btn" style="flex:1;">Save and resolve</button>
        <button id="rs-cancel" class="ghost-btn">Cancel</button>
      </div>
    `;
    overlay.appendChild(box);
    document.body.appendChild(overlay);
    box.querySelector('#rs-cancel')?.addEventListener('click', () => {
      document.body.removeChild(overlay);
      resolve(null);
    });
    box.querySelector('#rs-ok')?.addEventListener('click', () => {
      const done = String(box.querySelector('#rs-done')?.value || '').trim();
      const files = String(box.querySelector('#rs-files')?.value || '')
        .split(',').map((s) => s.trim()).filter(Boolean);
      document.body.removeChild(overlay);
      resolve({ done_summary: done, related_files: files });
    });
  });
}

async function updateStatus(id, status) {
  const project = getCurrentProject();
  if (!project.trim()) {
    showToast('Set a project first', 'error');
    return;
  }
  try {
    const current = itemsCache.get(id) || {};
    const type = (current.type || '').toLowerCase();
    if (status === 'resolved' && (type === 'bug' || type === 'todo')) {
      // If already valid, no prompt needed; otherwise collect data
      if (!hasValidResolutionMeta(current.meta || {})) {
        const data = await showResolveModal(current);
        if (!data) return; // cancelled
        const meta = { ...(current.meta || {}), done_summary: data.done_summary, related_files: data.related_files };
        await updateItem(project, id, { status, meta });
        showToast('Status updated', 'success');
        refreshItems();
        return;
      }
    }
    await updateItem(project, id, { status });
    showToast('Status updated', 'success');
    refreshItems();
  } catch (e) {
    log('Update status failed: ' + e.message);
    showToast(e.message || 'Failed to update status', 'error');
  }
}

function openItemModal(item) {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed; inset:0; background: rgba(0,0,0,0.6); display:flex; align-items:center; justify-content:center; z-index:1000; backdrop-filter: blur(2px);';
  const box = document.createElement('div');
  box.style.cssText = 'background: var(--bg-primary); border:1px solid var(--border-secondary); border-radius:10px; width: min(880px, 94vw); max-height: 86vh; overflow:auto; box-shadow: var(--shadow);';
  const header = document.createElement('div');
  header.style.cssText = 'position:sticky; top:0; background: var(--bg-primary); padding: 14px 16px; border-bottom:1px solid var(--border-secondary); display:flex; align-items:center; justify-content: space-between; gap:8px;';
  const title = document.createElement('div');
  title.style.cssText = 'font-size:16px; font-weight:700; color: var(--text-primary);';
  title.innerText = (item.title || '(untitled)');
  const close = document.createElement('button');
  close.className = 'ghost-btn';
  close.innerText = 'Close';
  close.addEventListener('click', () => document.body.removeChild(overlay));
  header.appendChild(title);
  header.appendChild(close);

  const body = document.createElement('div');
  body.style.cssText = 'padding: 14px 16px; display:grid; grid-template-columns: 1fr; gap:12px;';
  const metaRow = (label, valueHtml) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:grid; grid-template-columns: 140px 1fr; gap:10px; align-items:start;';
    const l = document.createElement('div'); l.style.cssText = 'font-size:12px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .04em;'; l.innerText = label;
    const v = document.createElement('div'); v.style.cssText = 'font-size:13px; color: var(--text-primary);'; v.innerHTML = valueHtml;
    row.appendChild(l); row.appendChild(v);
    return row;
  };
  const esc = (s) => escapeHtml(String(s ?? ''));
  const list = (arr) => Array.isArray(arr) && arr.length ? '<ul style="margin:0; padding-left: 18px;">' + arr.map((x)=>`<li style="margin:2px 0;">${esc(x)}</li>`).join('') + '</ul>' : '-';

  // Basic
  body.appendChild(metaRow('Type', esc(item.type || '')));
  body.appendChild(metaRow('Version', esc(item.version || '')));
  body.appendChild(metaRow('Status', esc(item.status || '')));
  body.appendChild(metaRow('Tags', (item.tags||[]).length ? esc((item.tags||[]).join(', ')) : '-'));

  // Typed block (by type)
  const t = (item.type || '').toLowerCase();
  const typed = item.typed || {};
  if (t === 'bug') {
    body.appendChild(metaRow('Severity', esc(typed.severity || '-')));
    body.appendChild(metaRow('Expected', esc(typed.expected || '-')));
    body.appendChild(metaRow('Reproduction', `<div style="white-space:pre-wrap;">${esc(typed.reproduction || '-')}</div>`));
    body.appendChild(metaRow('Root cause', `<div style="white-space:pre-wrap;">${esc(typed.root_cause || '-')}</div>`));
  } else if (t === 'todo') {
    body.appendChild(metaRow('Kind', esc(typed.kind || '-')));
    body.appendChild(metaRow('Priority', esc(typed.priority || '-')));
    body.appendChild(metaRow('Acceptance', list(typed.acceptance_criteria || [])));
  } else if (t === 'memory') {
    body.appendChild(metaRow('Topic', esc(typed.topic || '-')));
    body.appendChild(metaRow('Decision', esc(typed.decision || '-')));
    body.appendChild(metaRow('Context', `<div style="white-space:pre-wrap;">${esc(typed.context || '-')}</div>`));
    body.appendChild(metaRow('Rationale', `<div style="white-space:pre-wrap;">${esc(typed.rationale || '-')}</div>`));
  } else if (t === 'doc') {
    body.appendChild(metaRow('Authors', list(typed.authors || [])));
    body.appendChild(metaRow('Related docs', list(typed.related_docs || [])));
  }

  // Meta extras
  const m = item.meta || {};
  if (m.done_summary) body.appendChild(metaRow('Done summary', `<div style="white-space:pre-wrap;">${esc(m.done_summary)}</div>`));
  if (m.related_files) body.appendChild(metaRow('Related files', list(m.related_files)));
  if (m.logs_excerpt) body.appendChild(metaRow('Logs', `<div style="white-space:pre-wrap;">${esc(m.logs_excerpt)}</div>`));
  if (m.resolution_criteria) body.appendChild(metaRow('Criteria', list(m.resolution_criteria)));
  if (m.screenshots) {
    const screenshots = Array.isArray(m.screenshots) ? m.screenshots : [];
    const links = screenshots.map((u) => {
      const url = String(u || '');
      if (!isValidUrl(url)) return esc(url);
      return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer" style="color:#3b82f6; text-decoration:none;">${esc(url)}</a>`;
    });
    body.appendChild(metaRow('Screenshots', links.length ? links.join('<br/>') : '-'));
  }

  // Body
  if (item.body_md && item.body_md.trim()) {
    const section = document.createElement('div');
    section.style.cssText = 'margin-top: 6px; padding-top: 6px; border-top:1px dashed var(--border-secondary);';
    section.innerHTML = '<div style="font-size:12px; color: var(--text-tertiary); text-transform: uppercase; letter-spacing: .04em; margin-bottom:6px;">Body</div>' +
      `<div style="font-size:13px; color: var(--text-secondary); white-space: pre-wrap;">${esc(item.body_md)}</div>`;
    body.appendChild(section);
  }

  box.appendChild(header);
  box.appendChild(body);
  overlay.appendChild(box);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) document.body.removeChild(overlay); });
  document.body.appendChild(overlay);
}

export async function deleteItem(id) {
  const project = getCurrentProject();
  if (!project.trim()) {
    showToast('Set a project first', 'error');
    return;
  }
  try {
    await apiDeleteItem(project, id);
    showToast('Item deleted', 'success');
    refreshItems();
  } catch (e) {
    log('Delete failed: ' + e.message);
    showToast(e.message || 'Failed to delete item', 'error');
  }
}

export async function updateItemMeta() {
  const project = document.getElementById('items-project')?.value || '';
  const id = document.getElementById('edit-item-id')?.value || '';
  if (!project.trim() || !id.trim()) {
    showToast('Set project and item id', 'error');
    return;
  }
  const fields = {};
  const title = document.getElementById('edit-title')?.value || '';
  const status = document.getElementById('edit-status')?.value || '';
  const tags = document.getElementById('edit-tags')?.value || '';
  const meta = parseJsonSafe(document.getElementById('edit-meta')?.value, null);
  if (title) fields.title = title;
  if (status) fields.status = status;
  if (tags) fields.tags = parseTags(tags);
  if (meta !== null) fields.meta = meta;
  try {
    await updateItem(project, id, fields);
    showToast('Item updated', 'success');
    refreshItems();
  } catch (e) {
    log('Update item failed: ' + e.message);
    showToast(e.message || 'Failed to update item', 'error');
  }
}

export function registerGlobals() {
  window.setMemoryType = setMemoryType;
  window.applyMetaTemplate = applyMetaTemplate;
  window.createItem = createItem;
  window.refreshItems = refreshItems;
  window.clearItems = clearItems;
  window.updateItemMeta = updateItemMeta;
  window.deleteItem = deleteItem;
}

export function init() {
  populateStatusSelects();
  updateMetaGuidance();
  setMemoryType(getCurrentItemType());
}

export function onShow() {
  populateStatusSelects();
  updateMetaGuidance();
}
