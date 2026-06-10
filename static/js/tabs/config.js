import { getProjects, createProject, deleteProject as apiDeleteProject, getSettings, saveSettings as apiSaveSettings, getTools, saveTools as apiSaveTools, restartMcp as apiRestartMcp } from '../core/api.js';
import { normalizeSlug, setButtonLoading } from '../core/utils.js';
import { showToast } from '../core/toast.js';
import { log } from '../core/logger.js';
import { setCurrentProject, state } from '../core/state.js';

function _clearChildren(el) {
  if (!el) return;
  while (el.firstChild) el.removeChild(el.firstChild);
}

function updateToolsRestartBanner() {
  const banner = document.getElementById('tools-restart-banner');
  if (!banner) return;
  banner.classList.toggle('hidden', !state.toolsNeedRestart);
}

function updateSettingsRestartBanner() {
  const banner = document.getElementById('settings-restart-banner');
  if (!banner) return;
  banner.classList.toggle('hidden', !state.settingsNeedRestart);
}

function updateProjectSlugHint() {
  const input = document.getElementById('config-project');
  const hint = document.getElementById('project-slug-status');
  if (!input || !hint) return;
  const raw = input.value || '';
  const norm = normalizeSlug(raw);
  if (!raw.trim()) {
    hint.style.color = 'var(--text-tertiary)';
    _clearChildren(hint);
    hint.textContent = 'Enter a project slug. It will be normalized to lowercase and dashes.';
    return;
  }
  if (norm !== raw) {
    hint.style.color = '#d97706';
    _clearChildren(hint);
    hint.appendChild(document.createTextNode('Will be saved as: '));
    const code = document.createElement('code');
    code.style.cssText = 'color: var(--text-secondary);';
    code.textContent = norm;
    hint.appendChild(code);
  } else {
    hint.style.color = '#22c55e';
    _clearChildren(hint);
    hint.textContent = 'Looks good ✓';
  }
}

export async function refreshProjects(event) {
  log('Refreshing projects list...');
  const btn = event?.target;
  const withAnimation = !!btn;
  if (btn) setButtonLoading(btn, true);
  const list = document.getElementById('projects-list');
  if (!list) return;
  if (withAnimation) {
    _clearChildren(list);
    for (let i = 0; i < 4; i += 1) {
      const sk = document.createElement('li');
      sk.className = 'stagger-item';
      const div = document.createElement('div');
      div.className = 'skeleton';
      div.style.cssText = 'height: 46px; border-radius: 6px;';
      sk.appendChild(div);
      list.appendChild(sk);
    }
  }
  try {
    const data = await getProjects();
    _clearChildren(list);
    (data.projects || []).forEach((p) => {
      const li = document.createElement('li');
      const isActive = String(p.slug) === String(state.currentProjectSlug);
      li.className = withAnimation ? 'stagger-item' : '';
      li.style.cssText = 'padding: 8px; border: 1px solid var(--border-secondary); border-radius: 6px; display: flex; align-items: center; justify-content: space-between; gap: 8px;';

      const left = document.createElement('div');
      const top = document.createElement('div');
      top.style.cssText = 'font-weight:600; color: var(--text-primary);';
      top.textContent = (p.slug ?? '').toString();
      if (isActive) {
        const active = document.createElement('span');
        active.style.cssText = 'margin-left:6px; font-size:11px; color:#22c55e;';
        active.textContent = '(active)';
        top.appendChild(active);
      }
      const bottom = document.createElement('div');
      bottom.style.cssText = 'font-size:12px; color: var(--text-tertiary);';
      const pname = (p.name ?? '').toString().trim() || '-';
      bottom.textContent = `${pname} · ${p.items_count || 0} items`;
      left.appendChild(top);
      left.appendChild(bottom);

      const actions = document.createElement('div');
      actions.style.cssText = 'display:flex; gap:6px;';
      const useBtn = document.createElement('button');
      useBtn.className = 'ghost-btn';
      useBtn.style.cssText = 'padding:4px 8px;';
      useBtn.textContent = 'Use';
      useBtn.addEventListener('click', () => selectProject(p.slug));
      const delBtn = document.createElement('button');
      delBtn.className = 'ghost-btn';
      delBtn.style.cssText = 'padding:4px 8px;';
      delBtn.title = isActive ? 'You cannot delete the active project' : 'Delete this project (removes all associated items)';
      delBtn.textContent = 'Delete';
      delBtn.addEventListener('click', () => deleteProject(p.slug));
      actions.appendChild(useBtn);
      actions.appendChild(delBtn);

      li.appendChild(left);
      li.appendChild(actions);
      list.appendChild(li);
    });
    if ((data.projects || []).length === 0) {
      const li = document.createElement('li');
      li.style.cssText = 'color: var(--text-quaternary); font-size: 12px;';
      li.textContent = 'No projects yet';
      list.appendChild(li);
    }
  } catch (e) {
    showToast('Failed to load projects', 'error');
  } finally {
    if (btn) setButtonLoading(btn, false);
  }
}

export async function selectProject(slug) {
  const norm = normalizeSlug(slug || '');
  if (!norm) { showToast('Invalid project slug', 'error'); return; }
  const input = document.getElementById('config-project');
  if (input) input.value = norm;
  try {
    await apiSaveSettings({ selected_project: norm });
    setCurrentProject(norm);
    updateProjectSlugHint();
    showToast(`Selected ${norm}`, 'success');
  } catch (e) {
    showToast(e.message || 'Failed to save selected project', 'error');
  }
  refreshProjects();
}

export async function deleteProject(slug) {
  if (!slug || !String(slug).trim()) { showToast('Invalid project slug', 'error'); return; }
  if (String(slug) === String(state.currentProjectSlug)) {
    showToast('You cannot delete the active project. Change the selection first.', 'error');
    return;
  }
  const warning = [
    'You are about to delete the project:',
    `- ${slug}`,
    '',
    'This will permanently delete ALL items associated with this project:',
    '- memory, doc, bug and todo items',
    '',
    'This action cannot be undone.',
    '',
    'Do you want to continue?',
  ].join('\n');
  const proceed = confirm(warning);
  if (!proceed) { showToast('Deletion cancelled', 'success'); return; }
  const typed = prompt('Type the project slug to confirm deletion:');
  if (typed === null) { showToast('Deletion cancelled', 'success'); return; }
  if (String(typed).trim() !== String(slug)) {
    showToast('Project slug does not match; deletion aborted', 'error');
    return;
  }
  log(`Deleting project '${slug}'...`);
  try {
    const data = await apiDeleteProject(slug);
    showToast(`Project '${slug}' deleted (${data.deleted_items || 0} items removed)`, 'success');
    refreshProjects();
  } catch (e) {
    log('Delete project failed: ' + e.message);
    showToast(e.message || 'Failed to delete project', 'error');
  }
}

export function gotoProjectSettings() {
  const configTab = document.querySelector('.tab-btn[data-tab="config"]');
  if (configTab) configTab.click();
  const settingsBtn = document.querySelector('#tab-config .tab-btn[data-subtab="config-settings"]');
  if (settingsBtn) settingsBtn.click();
  setTimeout(() => {
    const inp = document.getElementById('config-project');
    if (inp) inp.focus();
  }, 50);
}

export async function saveSelectedProject(event) {
  const input = document.getElementById('config-project');
  const btn = event?.target;
  let slug = input?.value ? input.value.trim() : '';
  if (!slug) { showToast('Set a project slug first', 'error'); return; }
  slug = normalizeSlug(slug);
  if (input && input.value !== slug) input.value = slug;
  if (btn) setButtonLoading(btn, true);
  try {
    try {
      await createProject(slug, undefined);
      showToast(`Project created and set: ${slug}`, 'success');
    } catch (e) {
      if (e.message && e.message.includes('exists')) {
        log(`Project already exists: ${slug}. Selecting it.`);
      } else {
        throw e;
      }
    }
    await apiSaveSettings({ selected_project: slug });
    setCurrentProject(slug);
    updateProjectSlugHint();
    refreshProjects();
    showToast(`Project selected: ${slug}`, 'success');
  } catch (e) {
    log('Save selected project failed: ' + e.message);
    showToast(e.message || 'Failed to save selected project', 'error');
  } finally {
    if (btn) setButtonLoading(btn, false);
  }
}

export async function refreshSettings() {
  try {
    const data = await getSettings();
    const mode = document.getElementById('mode-select'); if (mode) mode.value = data.mode || 'local';
    const embL = document.getElementById('embedding-local'); if (embL) embL.value = data.embedding_local || '';
    const embC = document.getElementById('embedding-cloud'); if (embC) embC.value = data.embedding_cloud || '';
    const rerL = document.getElementById('reranker-local'); if (rerL) rerL.value = data.reranker_local || '';
    const rerC = document.getElementById('reranker-cloud'); if (rerC) rerC.value = data.reranker_cloud || '';
    const enableR = document.getElementById('enable-rerank'); if (enableR) enableR.checked = !!data.enable_rerank;
    const proj = (data.selected_project || '').trim();
    const projInput = document.getElementById('config-project'); if (projInput) projInput.value = proj;
    setCurrentProject(proj);
    updateProjectSlugHint();
    const rebuild = document.getElementById('needs-rebuild'); if (rebuild) rebuild.style.display = data.needs_rebuild ? 'block' : 'none';
    state.settingsNeedRestart = !!data.needs_restart;
    updateSettingsRestartBanner();
    state.toolsNeedRestart = state.toolsNeedRestart || state.settingsNeedRestart;
    updateToolsRestartBanner();
    const pj = document.getElementById('config-project');
    if (pj && !pj.dataset.hooked) {
      pj.addEventListener('input', updateProjectSlugHint);
      pj.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); saveSelectedProject(e); } });
      pj.dataset.hooked = '1';
    }
  } catch (e) {
    log('Error loading settings: ' + e.message);
  }
}

export async function saveSettings(event) {
  const payload = {
    mode: document.getElementById('mode-select')?.value,
    embedding_local: (document.getElementById('embedding-local')?.value || '').trim(),
    embedding_cloud: (document.getElementById('embedding-cloud')?.value || '').trim(),
    reranker_local: (document.getElementById('reranker-local')?.value || '').trim(),
    reranker_cloud: (document.getElementById('reranker-cloud')?.value || '').trim(),
    enable_rerank: document.getElementById('enable-rerank')?.checked || false,
  };
  const btn = event?.target;
  if (btn) setButtonLoading(btn, true);
  log('Saving settings...');
  try {
    const data = await apiSaveSettings(payload);
    const needsRebuild = document.getElementById('needs-rebuild');
    if (needsRebuild) needsRebuild.style.display = data.needs_rebuild ? 'block' : 'none';
    state.settingsNeedRestart = !!data.needs_restart;
    state.toolsNeedRestart = state.toolsNeedRestart || state.settingsNeedRestart;
    updateSettingsRestartBanner();
    updateToolsRestartBanner();
    const message = data.needs_rebuild
      ? 'Saved to config.yaml. Restart MCP and rebuild index to apply.'
      : 'Saved to config.yaml.';
    showToast(message, 'success');
  } catch (e) {
    log('Error saving settings: ' + e.message);
    showToast('Error saving settings', 'error');
  } finally {
    if (btn) setButtonLoading(btn, false);
  }
}

export async function refreshTools() {
  log('Loading tools...');
  try {
    const data = await getTools();
    const container = document.getElementById('tools-groups');
    const enabled = data.enabled || [];
    const toolGroups = data.groups || {};
    state.toolsNeedRestart = !!data.needs_restart;
    updateToolsRestartBanner();
    if (!container) return;
    _clearChildren(container);
    const isLight = document.body.classList.contains('light-mode');
    const hoverBg = isLight ? 'rgba(0, 0, 0, 0.03)' : 'rgba(255, 255, 255, 0.03)';
    Object.entries(toolGroups).forEach(([group, names]) => {
      const card = document.createElement('div');
      card.style.cssText = 'padding: 12px; background: var(--bg-tertiary); border: 1px solid var(--border-secondary); border-radius: 6px; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);';
      const nice = (group || '').replace(/_/g, ' ').replace(/\b[a-z]/g, (m) => m.toUpperCase());
      const header = document.createElement('div');
      header.style.cssText = 'font-size: 10px; text-transform: uppercase; letter-spacing: 0.05em; color: var(--text-tertiary); font-weight: 600; margin-bottom: 10px;';
      header.textContent = nice;
      card.appendChild(header);
      names.forEach((name) => {
        const id = `tool-${group}-${name}`;
        const row = document.createElement('div');
        row.style.cssText = 'display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 4px; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);';
        row.onmouseover = () => { row.style.background = hoverBg; row.style.transform = 'translateX(4px)'; };
        row.onmouseout = () => { row.style.background = 'transparent'; row.style.transform = 'translateX(0)'; };
        const chk = document.createElement('input');
        chk.type = 'checkbox';
        chk.id = id;
        chk.dataset.tool = name;
        chk.checked = enabled.includes(name);
        const label = document.createElement('label');
        label.htmlFor = id;
        label.style.cssText = 'font-size: 13px; color: var(--text-primary); cursor: pointer; flex: 1;';
        label.textContent = name;
        row.appendChild(chk);
        row.appendChild(label);
        card.appendChild(row);
      });
      container.appendChild(card);
    });
  } catch (e) {
    log('Error fetching tools: ' + e.message);
  }
}

export async function saveTools(event) {
  const selected = [];
  document.querySelectorAll('#tools-groups input[type=checkbox]').forEach((chk) => {
    if (chk.checked) selected.push(chk.dataset.tool);
  });
  log('Saving tools: ' + selected.join(', '));
  const btn = event?.target;
  setButtonLoading(btn, true);
  try {
    await apiSaveTools(selected);
    log('Tools saved to config.yaml (restart required)');
    state.toolsNeedRestart = true;
    updateToolsRestartBanner();
    showToast('Saved to config.yaml. Restart MCP to apply.', 'success');
  } catch (e) {
    log('Error saving tools: ' + e.message);
    showToast('Error saving tools', 'error');
  } finally {
    setButtonLoading(btn, false);
  }
}

export async function restartMcp(event) {
  const btn = event?.target;
  log('Requesting MCP restart...');
  if (btn) setButtonLoading(btn, true);
  try {
    await apiRestartMcp();
    showToast('Restarting MCP (container if configured)...', 'success');
    log('Restart requested; container or process will relaunch with updated config.');
    state.toolsNeedRestart = false;
    state.settingsNeedRestart = false;
    updateToolsRestartBanner();
    updateSettingsRestartBanner();
  } catch (e) {
    if (e.message && e.message.includes('CONTAINER_NAME')) {
      showToast('Restart unavailable: set CONTAINER_NAME in Docker env.', 'error');
    } else {
      showToast('Failed to restart MCP server', 'error');
    }
    log('Restart request failed: ' + e.message);
  } finally {
    if (btn) setButtonLoading(btn, false);
  }
}

export function registerGlobals() {
  window.refreshProjects = refreshProjects;
  window.selectProject = selectProject;
  window.deleteProject = deleteProject;
  window.saveSelectedProject = saveSelectedProject;
  window.gotoProjectSettings = gotoProjectSettings;
  window.refreshSettings = refreshSettings;
  window.saveSettings = saveSettings;
  window.refreshTools = refreshTools;
  window.saveTools = saveTools;
  window.restartMcp = restartMcp;
}

export async function init() {
  await refreshTools();
  await refreshSettings();
  await refreshProjects();
}

export function onShow() {
  refreshSettings();
}
