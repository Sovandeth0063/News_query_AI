/**
 * Theme Manager: Dark/Light Mode with localStorage persistence,
 * system preference sync, and manual override.
 */

const THEME_STORAGE_KEY = 'newsquery_theme';

export function initTheme() {
  const toggleBtn = document.getElementById('themeToggleBtn');
  const storedTheme = localStorage.getItem(THEME_STORAGE_KEY);

  // If already set by inline script in head, sync icon
  const currentTheme = document.documentElement.getAttribute('data-theme') || 
    (storedTheme || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'));

  setTheme(currentTheme, false);

  if (toggleBtn) {
    toggleBtn.addEventListener('click', toggleTheme);
  }

  // Only listen to OS changes if user hasn't explicitly chosen a manual theme
  if (!storedTheme) {
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleSystemChange = (e) => {
      if (!localStorage.getItem(THEME_STORAGE_KEY)) {
        setTheme(e.matches ? 'dark' : 'light', false);
      }
    };
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', handleSystemChange);
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(handleSystemChange);
    }
  }
}

export function setTheme(theme, saveManual = true) {
  document.documentElement.setAttribute('data-theme', theme);
  if (saveManual) {
    localStorage.setItem(THEME_STORAGE_KEY, theme);
  }

  const toggleBtn = document.getElementById('themeToggleBtn');
  if (toggleBtn) {
    const isDark = theme === 'dark';
    toggleBtn.setAttribute('aria-label', `Switch to ${isDark ? 'light' : 'dark'} theme`);
    toggleBtn.setAttribute('title', `Switch to ${isDark ? 'light' : 'dark'} theme`);
    toggleBtn.innerHTML = isDark
      ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="5"></circle><line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line></svg>`
      : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path></svg>`;
  }
}

export function toggleTheme() {
  const active = document.documentElement.getAttribute('data-theme') || 'dark';
  const nextTheme = active === 'dark' ? 'light' : 'dark';
  setTheme(nextTheme, true);
}
