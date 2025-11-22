import { boardStatuses, getCurrentProject, setCurrentProject, setCurrentItemType, getCurrentItemType } from '../core/state.js';
import { parseJsonSafe, parseTags, escapeHtml } from '../core/utils.js';
import { createItem as apiCreateItem, listItems, updateItem, replaceItemBody, deleteItem as apiDeleteItem } from '../core/api.js';
import { showToast } from '../core/toast.js';
import { log } from '../core/logger.js';

function getMetaTemplate(type) {
  switch ((type || '').toLowerCase()) {
    case 'bug':
      return JSON.stringify({
        severity: 'high|medium|low',
        reproduction: 'steps to reproduce... (#1, #2, #3)',
        logs_excerpt: 'copy here the most relevant log lines',
        expected: 'what should have happened instead',
        root_cause: 'short summary of the root cause',
        fix_summary: 'what should we change and why',
        fixed_in_commit: '',
      }, null, 2);
    case 'todo':
      return JSON.stringify({
        kind: 'bug_fix|refactor|feature|chore',
        reproduction: 'optional, only for bug-like tasks',
        acceptance_criteria: [
          'criterion 1',
          'criterion 2',
        ],
        dependencies: [],
        priority: 'p0|p1|p2',
      }, null, 2);
    case 'doc':
      return JSON.stringify({
        authors: ['name <email>'],
        source_url: '',
        related_docs: [],
        version_notes: 'what changed and when',
      }, null, 2);
    case 'memory':
    default:
      return JSON.stringify({
        topic: 'short topic',
        decision: 'what is decided or the invariant to keep',
        context: 'why we chose this; constraints; alternatives',
        rationale: 'trade-offs and reasoning',
        related_links: [],
      }, null, 2);
  }
}

function getMetaHelp(type) {
  switch ((type || '').toLowerCase()) {
    case 'bug':
      return 'Suggested fields: severity (high|medium|low), reproduction (steps), logs_excerpt, expected, root_cause, fix_summary, fixed_in_commit. You can add or remove fields freely.';
    case 'todo':
      return 'Suggested fields: kind (bug_fix|refactor|feature|chore), reproduction (optional), acceptance_criteria (list), dependencies (list), priority (p0|p1|p2). You can add or remove fields freely.';
    case 'doc':
      return 'Suggested fields: authors, source_url, related_docs, version_notes. You can add or remove fields freely.';
    case 'memory':
    default:
      return 'Suggested fields: topic, decision, context, rationale, related_links. You can add or remove fields freely.';
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
  const meta = parseJsonSafe(document.getElementById('item-meta')?.value, {});
  const body_md = document.getElementById('item-body')?.value || '';
  if (!project.trim()) { showToast('Select a project in Settings', 'error'); return; }
  log('Creating item...');
  try {
    await apiCreateItem({ project, type, title, body_md, tags, status, meta });
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
  if (getCurrentItemType() === 'todo') {
    board.style.display = 'grid';
    list.style.display = 'none';
    renderBoard(items);
  } else {
    board.style.display = 'none';
    list.style.display = 'grid';
    renderList(items);
  }
}

function renderList(items) {
  const list = document.getElementById('list');
  if (!list) return;
  list.innerHTML = '';
  (items || []).forEach((item) => {
    const card = document.createElement('div');
    card.style.cssText = 'background: var(--bg-secondary); border: 1px solid var(--border-hover); border-radius: 6px; padding: 12px; box-shadow: var(--shadow);';
    const header = document.createElement('div');
    header.style.cssText = 'display:flex; align-items:center; justify-content: space-between; gap:8px; margin-bottom:6px;';
    const left = document.createElement('div');
    left.innerHTML = `<div style="font-weight:600; color: var(--text-primary);">${escapeHtml(item.title || '(untitled)')}</div><div style="font-size:11px; color: var(--text-tertiary);">${item.type || ''} · v${item.version || ''}</div>`;
    const actions = document.createElement('div');
    actions.style.cssText = 'display:flex; gap:6px;';
    const editBtn = document.createElement('button');
    editBtn.className = 'ghost-btn';
    editBtn.style.cssText = 'padding:6px 8px;';
    editBtn.innerHTML = '✎';
    editBtn.title = 'Edit item';
    editBtn.addEventListener('click', () => toggleInlineEdit(card, item));
    const delBtn = document.createElement('button');
    delBtn.className = 'ghost-btn';
    delBtn.style.cssText = 'padding:6px 8px; color:#ef4444; border-color: rgba(239,68,68,0.4);';
    delBtn.innerText = 'Delete';
    delBtn.addEventListener('click', () => deleteItem(item.id));
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
  try {
    if (Object.keys(fields).length > 0) {
      const res = await updateItem(project, item.id, fields);
      item = res.item || item;
    }
    if (typeof newBody === 'string') {
      await replaceItemBody(project, item.id, newBody, item.version);
    }
    showToast('Item saved', 'success');
    refreshItems();
  } catch (e) {
    log('Inline update failed: ' + e.message);
    showToast(e.message || 'Failed to update item', 'error');
  }
}

function renderBoard(items) {
  const board = document.getElementById('board');
  if (!board) return;
  board.innerHTML = '';
  const byStatus = {};
  items.forEach((item) => {
    const statusKey = (item.status || 'pending').toLowerCase();
    byStatus[statusKey] = byStatus[statusKey] || [];
    byStatus[statusKey].push(item);
  });

  boardStatuses.forEach((status) => {
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

      const editBtn = document.createElement('button');
      editBtn.className = 'ghost-btn';
      editBtn.style.cssText = 'padding:6px 8px;';
      editBtn.innerHTML = '✎';
      editBtn.title = 'Edit item';
      editBtn.addEventListener('click', () => toggleInlineEdit(card, item));

      const delBtn = document.createElement('button');
      delBtn.className = 'ghost-btn';
      delBtn.style.cssText = 'padding:6px 8px; color:#ef4444; border-color: rgba(239,68,68,0.4);';
      delBtn.innerText = 'Delete';
      delBtn.addEventListener('click', () => deleteItem(item.id));

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

async function updateStatus(id, status) {
  const project = getCurrentProject();
  if (!project.trim()) {
    showToast('Set a project first', 'error');
    return;
  }
  try {
    await updateItem(project, id, { status });
    showToast('Status updated', 'success');
    refreshItems();
  } catch (e) {
    log('Update status failed: ' + e.message);
    showToast(e.message || 'Failed to update status', 'error');
  }
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
