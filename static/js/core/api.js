async function requestJson(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: options.json === false
      ? options.headers
      : { 'Content-Type': 'application/json', ...(options.headers || {}) },
    body: options.body && options.json !== false ? JSON.stringify(options.body) : options.body,
  });
  const contentType = res.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  const payload = isJson ? await res.json().catch(() => ({})) : await res.text();
  if (!res.ok) {
    const detail = (payload && payload.detail) ? payload.detail : res.statusText;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return payload;
}

export function getStatus() {
  return requestJson('/ui/api/status');
}

export function getTools() {
  return requestJson('/ui/api/tools');
}

export function saveTools(enabled) {
  return requestJson('/ui/api/tools', { method: 'POST', body: { enabled } });
}

export function getSettings() {
  return requestJson('/ui/api/settings');
}

export function saveSettings(payload) {
  return requestJson('/ui/api/settings', { method: 'POST', body: payload });
}

export function getUrlFiles() {
  return requestJson('/ui/api/url-files');
}

export function rebuildSitemap(url) {
  return requestJson('/ui/api/rebuild/sitemap', { method: 'POST', body: { url } });
}

export function rebuildFile(filename) {
  return requestJson('/ui/api/rebuild/url-file', { method: 'POST', body: { filename } });
}

export function getDocs() {
  return requestJson('/ui/api/docs');
}

export function getProjects() {
  return requestJson('/ui/api/projects');
}

export function createProject(slug, name) {
  return requestJson('/ui/api/projects', { method: 'POST', body: { slug, name } });
}

export function deleteProject(slug) {
  return requestJson(`/ui/api/projects/${encodeURIComponent(slug)}`, { method: 'DELETE' });
}

export function listItems(params) {
  const search = new URLSearchParams(params || {});
  return requestJson(`/ui/api/items?${search.toString()}`);
}

export function createItem(payload) {
  return requestJson('/ui/api/items', { method: 'POST', body: payload });
}

export function updateItem(project, id, fields) {
  return requestJson(`/ui/api/items/${id}`, { method: 'PATCH', body: { project, fields } });
}

export function replaceItemBody(project, id, body_md, expected_version) {
  return requestJson(`/ui/api/items/${id}/body`, {
    method: 'POST',
    body: { project, body_md, expected_version },
  });
}

export function deleteItem(project, id) {
  return requestJson(`/ui/api/items/${id}?project=${encodeURIComponent(project)}`, { method: 'DELETE' });
}

export function restartMcp() {
  return requestJson('/ui/api/restart', { method: 'POST' });
}

export async function getGuidelines() {
  const res = await fetch('/ui/api/guidelines');
  if (!res.ok) {
    throw new Error('Failed to load guidelines');
  }
  return res.text();
}
