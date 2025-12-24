const _SVG_NS = 'http://www.w3.org/2000/svg';

function _buildToastIcon(type) {
  const kind = (type || 'success').toString().trim().toLowerCase() === 'error' ? 'error' : 'success';
  const svg = document.createElementNS(_SVG_NS, 'svg');
  svg.setAttribute('style', `width: 16px; height: 16px; color: ${kind === 'success' ? '#22c55e' : '#ef4444'};`);
  svg.setAttribute('fill', 'none');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('stroke', 'currentColor');
  const path = document.createElementNS(_SVG_NS, 'path');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  path.setAttribute('stroke-width', '2');
  path.setAttribute('d', kind === 'success' ? 'M5 13l4 4L19 7' : 'M6 18L18 6M6 6l12 12');
  svg.appendChild(path);
  return svg;
}

export function showToast(message, type = 'success') {
  const kind = (type || 'success').toString().trim().toLowerCase() === 'error' ? 'error' : 'success';
  const toast = document.createElement('div');
  toast.className = `toast ${kind}`;

  toast.appendChild(_buildToastIcon(kind));

  const span = document.createElement('span');
  span.textContent = (message ?? '').toString();
  toast.appendChild(span);

  document.body.appendChild(toast);

  toast.animate([
    { transform: 'scale(0.9)', opacity: 0 },
    { transform: 'scale(1.02)', opacity: 1 },
    { transform: 'scale(1)', opacity: 1 },
  ], {
    duration: 300,
    easing: 'cubic-bezier(0.68, -0.55, 0.27, 1.55)',
  });

  setTimeout(() => {
    toast.style.animation = 'slideIn 0.3s ease reverse';
    setTimeout(() => toast.remove(), 300);
  }, 3000);
}
