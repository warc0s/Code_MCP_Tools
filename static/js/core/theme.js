export function toggleTheme() {
  const body = document.body;
  const isDark = !body.classList.contains('light-mode');
  if (isDark) {
    body.classList.add('light-mode');
    localStorage.setItem('theme', 'light');
    const darkIcon = document.getElementById('theme-icon-dark');
    const lightIcon = document.getElementById('theme-icon-light');
    if (darkIcon) darkIcon.classList.add('hidden');
    if (lightIcon) lightIcon.classList.remove('hidden');
  } else {
    body.classList.remove('light-mode');
    localStorage.setItem('theme', 'dark');
    const darkIcon = document.getElementById('theme-icon-dark');
    const lightIcon = document.getElementById('theme-icon-light');
    if (darkIcon) darkIcon.classList.remove('hidden');
    if (lightIcon) lightIcon.classList.add('hidden');
  }
}

export function initTheme() {
  const savedTheme = localStorage.getItem('theme');
  if (savedTheme === 'light') {
    document.body.classList.add('light-mode');
    const darkIcon = document.getElementById('theme-icon-dark');
    const lightIcon = document.getElementById('theme-icon-light');
    if (darkIcon) darkIcon.classList.add('hidden');
    if (lightIcon) lightIcon.classList.remove('hidden');
  }
}
