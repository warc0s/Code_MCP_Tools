import { initTheme, toggleTheme } from './core/theme.js';
import { state, setCurrentProject } from './core/state.js';
import { log } from './core/logger.js';

const tabModules = {
  dashboard: () => import('./tabs/dashboard.js'),
  rag: () => import('./tabs/rag.js'),
  memory: () => import('./tabs/memory.js'),
  config: () => import('./tabs/config.js'),
  log: () => import('./tabs/logs.js'),
};

const loaded = {};

async function ensureModule(name) {
  if (!tabModules[name]) return null;
  if (!loaded[name]) {
    loaded[name] = await tabModules[name]();
    if (loaded[name].registerGlobals) loaded[name].registerGlobals();
    if (loaded[name].init) await loaded[name].init();
  }
  return loaded[name];
}

// Fallbacks so header buttons work even before the full module loads.
window.gotoProjectSettings = () => ensureModule('config').then((mod) => mod?.gotoProjectSettings && mod.gotoProjectSettings());
window.toggleTheme = toggleTheme;

function setActiveTab(name) {
  document.querySelectorAll('.tab-btn[data-tab]').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.tab === name);
  });
  document.querySelectorAll('.tab-content').forEach((tab) => {
    tab.classList.toggle('hidden', tab.id !== `tab-${name}`);
  });
}

async function handleTabClick(name) {
  setActiveTab(name);
  const mod = await ensureModule(name);
  if (mod && mod.onShow) mod.onShow();
}

function setupTabNavigation() {
  document.querySelectorAll('.tab-btn[data-tab]').forEach((btn) => {
    btn.addEventListener('click', () => handleTabClick(btn.dataset.tab));
  });
}

function handleSubtabSwitch(subtabBtn) {
  const subtabName = subtabBtn.dataset.subtab;
  const parentTab = subtabBtn.closest('.tab-content');
  if (!parentTab) return;
  parentTab.querySelectorAll('.tab-btn[data-subtab]').forEach((b) => b.classList.remove('active'));
  parentTab.querySelectorAll('.subtab-content').forEach((t) => t.classList.add('hidden'));
  const newSubtab = document.getElementById(`subtab-${subtabName}`);
  if (newSubtab) newSubtab.classList.remove('hidden');
  subtabBtn.classList.add('active');
  dispatchSubtabAction(subtabName);
}

async function dispatchSubtabAction(name) {
  switch (name) {
    case 'dashboard-status': {
      const mod = await ensureModule('dashboard');
      if (mod?.refreshDashboardStatus) mod.refreshDashboardStatus();
      break;
    }
    case 'dashboard-guidelines': {
      const mod = await ensureModule('dashboard');
      if (mod?.loadGuidelines) mod.loadGuidelines();
      break;
    }
    case 'dashboard-integrations': {
      const mod = await ensureModule('dashboard');
      if (mod?.refreshIntegrations) mod.refreshIntegrations();
      break;
    }
    case 'rag-status': {
      const mod = await ensureModule('rag');
      if (mod?.refreshStatus) mod.refreshStatus();
      break;
    }
    case 'rag-docs': {
      const mod = await ensureModule('rag');
      if (mod?.refreshDocs) mod.refreshDocs();
      break;
    }
    case 'rag-settings': {
      const mod = await ensureModule('config');
      if (mod?.refreshSettings) mod.refreshSettings();
      break;
    }
    case 'config-settings': {
      const mod = await ensureModule('config');
      if (mod?.refreshSettings) mod.refreshSettings();
      break;
    }
    case 'config-tools': {
      const mod = await ensureModule('config');
      if (mod?.refreshTools) mod.refreshTools();
      break;
    }
    default:
      break;
  }
}

function setupSubtabs() {
  document.addEventListener('click', (e) => {
    const subtabBtn = e.target.closest('.tab-btn[data-subtab]');
    if (!subtabBtn) return;
    handleSubtabSwitch(subtabBtn);
  });
}

function bootstrap() {
  initTheme();
  window.toggleTheme = toggleTheme;
  setupTabNavigation();
  setupSubtabs();
  setCurrentProject('');
  ensureModule('config');
  handleTabClick('dashboard').then(() => {
    log('Dashboard loaded');
  });
}

document.addEventListener('DOMContentLoaded', bootstrap);
