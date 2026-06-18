export function log(message) {
  const area = document.getElementById('log');
  if (!area) return;
  const now = new Date().toLocaleTimeString();
  area.value = `[${now}] ${message}\n` + area.value;
}

export function clearLog() {
  const area = document.getElementById('log');
  if (area) area.value = '';
}
