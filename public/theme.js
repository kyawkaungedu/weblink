(() => {
  const control = document.getElementById('themeMode');
  const media = matchMedia('(prefers-color-scheme: dark)');
  let mode = 'system';
  try { mode = localStorage.getItem('link-lab-theme') || 'system'; } catch {}
  if (!['light', 'dark', 'system'].includes(mode)) mode = 'system';
  function apply() {
    document.documentElement.dataset.theme = mode === 'system' ? (media.matches ? 'dark' : 'light') : mode;
    control.value = mode;
  }
  control.addEventListener('change', () => {
    mode = control.value;
    try { localStorage.setItem('link-lab-theme', mode); } catch {}
    apply();
  });
  media.addEventListener('change', apply);
  apply();
})();
