export const state = {
  currentProjectSlug: '',
  currentItemType: 'memory',
  statusAuto: { id: null, active: false, notifiedDone: false },
  toolsNeedRestart: false,
  settingsNeedRestart: false,
};

export const boardStatuses = [
  { key: 'pending', label: 'Pending' },
  { key: 'in_progress', label: 'In progress' },
  { key: 'to_verify', label: 'To verify' },
  { key: 'resolved', label: 'Resolved' },
];

export function updateHeaderProject(slug) {
  const textEl = document.getElementById('header-project');
  const pill = document.getElementById('project-pill');
  const has = !!(slug && slug.trim());
  if (textEl) textEl.innerText = has ? slug.trim() : '-';
  if (pill) {
    if (has) {
      pill.style.background = 'rgba(59, 130, 246, 0.15)';
      pill.style.color = '#3b82f6';
      pill.style.border = '1px solid rgba(59, 130, 246, 0.3)';
    } else {
      pill.style.background = 'rgba(148, 163, 184, 0.12)';
      pill.style.color = 'var(--text-secondary)';
      pill.style.border = '1px solid var(--border-secondary)';
    }
  }
}

export function setCurrentProject(slug) {
  state.currentProjectSlug = (slug || '').trim();
  const hidden = document.getElementById('items-project');
  if (hidden) hidden.value = state.currentProjectSlug;
  updateHeaderProject(state.currentProjectSlug);
}

export function getCurrentProject() {
  if (state.currentProjectSlug && state.currentProjectSlug.trim()) return state.currentProjectSlug.trim();
  const hidden = document.getElementById('items-project');
  return hidden && hidden.value ? hidden.value.trim() : '';
}

export function setCurrentItemType(type) {
  state.currentItemType = (type || 'memory').trim() || 'memory';
}

export function getCurrentItemType() {
  return state.currentItemType || 'memory';
}

export function setRestartFlags({ tools, settings }) {
  if (typeof tools === 'boolean') state.toolsNeedRestart = tools;
  if (typeof settings === 'boolean') state.settingsNeedRestart = settings;
}
