export function showToast(message, type = 'success') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;

  const icon = type === 'success'
    ? '<svg style="width: 16px; height: 16px; color: #22c55e;" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" /></svg>'
    : '<svg style="width: 16px; height: 16px; color: #ef4444;" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" /></svg>';

  toast.innerHTML = icon + `<span>${message}</span>`;
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
