export function normalizeSlug(value) {
  const s = (value || '').toString().trim().toLowerCase();
  return s.replace(/[^a-z0-9-]+/g, '-').replace(/^-+|-+$/g, '').replace(/--+/g, '-');
}

export function parseJsonSafe(text, fallback) {
  if (!text || !text.trim()) return fallback;
  try {
    return JSON.parse(text);
  } catch (_) {
    return fallback;
  }
}

export function parseTags(value) {
  if (!value) return [];
  return value.split(',').map((t) => t.trim()).filter(Boolean);
}

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function isValidUrl(string) {
  try {
    const url = new URL(string);
    return url.protocol === 'http:' || url.protocol === 'https:';
  } catch (_) {
    return false;
  }
}

export function setButtonLoading(button, loading = true) {
  if (!button) return;
  // Be resilient to non-button targets (e.g., SVG/span inside the button)
  const btn = button.closest ? (button.closest('button') || button) : button;
  if (loading) {
    btn.classList.add('btn-loading');
    try { btn.disabled = true; } catch (_) { /* ignore */ }
  } else {
    btn.classList.remove('btn-loading');
    try { btn.disabled = false; } catch (_) { /* ignore */ }
  }
}
