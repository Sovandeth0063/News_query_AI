/**
 * Core Utilities: Security, Sanitization, Date & Focus Management
 */

const JUNK_DOMAINS = [
  'example.com', 'example.org', 'example.net',
  'localhost', '127.0.0.1', '0.0.0.0',
  'test.com', 'foo.com', 'bar.com',
  'placeholder', 'dummy'
];

/**
 * Validates that a URL uses http or https protocol and is not a script/data payload.
 * @param {string} url
 * @returns {boolean}
 */
export function isValidHttpUrl(url) {
  if (!url || typeof url !== 'string') return false;
  const trimmed = url.trim();
  if (!trimmed) return false;
  
  // Quick lower-case check for dangerous protocols
  const lower = trimmed.toLowerCase();
  if (lower.startsWith('javascript:') || lower.startsWith('data:') || lower.startsWith('vbscript:')) {
    return false;
  }
  
  try {
    const parsed = new URL(trimmed, window.location.origin);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch (e) {
    return false;
  }
}

/**
 * Client-side domain and integrity validation for feed items.
 * @param {object} article
 * @returns {boolean}
 */
export function isValidArticle(article) {
  if (!article || !article.title || !article.title.trim()) return false;
  if (!article.url || !isValidHttpUrl(article.url)) return false;
  const lowerUrl = article.url.toLowerCase();
  return !JUNK_DOMAINS.some(d => lowerUrl.includes(d));
}

/**
 * Strict HTML escaping for dynamic text interpolation.
 * @param {any} text
 * @returns {string}
 */
export function escapeHtml(text) {
  if (text === null || text === undefined) return '';
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/**
 * Parses ISO dates safely as UTC (handles missing timezone indicators)
 * and formats to a human relative string.
 * @param {string} isoDate
 * @returns {string}
 */
export function formatTimeAgo(isoDate) {
  if (!isoDate) return '';
  // Ensure UTC parsing if no timezone specified
  let safeIso = String(isoDate).trim();
  if (!safeIso.endsWith('Z') && !/[+-]\d{2}:\d{2}$/.test(safeIso)) {
    safeIso += 'Z';
  }
  const dt = new Date(safeIso);
  if (isNaN(dt.getTime())) return '';

  const now = new Date();
  const diffSec = Math.floor((now - dt) / 1000);

  if (diffSec < 0 || diffSec < 60) return 'Just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  const days = Math.floor(diffSec / 86400);
  if (days < 30) return `${days}d ago`;
  return dt.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export const formatRelativeTime = formatTimeAgo;

/**
 * Debounce helper with cancel capability.
 * @param {Function} func
 * @param {number} wait
 * @returns {Function}
 */
export function debounce(func, wait = 300) {
  let timeout;
  const debounced = function (...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func.apply(this, args), wait);
  };
  debounced.cancel = () => clearTimeout(timeout);
  return debounced;
}

/**
 * Safely parses markdown via local marked.js and purifies via local DOMPurify.
 * Ensures external links have noopener noreferrer.
 * @param {string} markdownText
 * @returns {string} Safe HTML string
 */
export function renderSafeMarkdown(markdownText) {
  if (!markdownText) return '';
  let rawHtml = '';
  if (window.marked && typeof window.marked.parse === 'function') {
    rawHtml = window.marked.parse(markdownText);
  } else {
    rawHtml = escapeHtml(markdownText).replace(/\n/g, '<br>');
  }

  if (window.DOMPurify && typeof window.DOMPurify.sanitize === 'function') {
    const clean = window.DOMPurify.sanitize(rawHtml, {
      ALLOWED_TAGS: [
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'br', 'hr',
        'ul', 'ol', 'li', 'strong', 'em', 'b', 'i', 'code', 'pre',
        'blockquote', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'a'
      ],
      ALLOWED_ATTR: ['href', 'title', 'target', 'rel']
    });

    // Post-process to ensure all anchors have target="_blank" and rel="noopener noreferrer"
    const tempDiv = document.createElement('div');
    tempDiv.innerHTML = clean;
    const links = tempDiv.querySelectorAll('a');
    links.forEach(a => {
      const href = a.getAttribute('href') || '';
      if (!isValidHttpUrl(href)) {
        a.removeAttribute('href');
        a.style.textDecoration = 'none';
      } else {
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener noreferrer');
      }
    });
    return tempDiv.innerHTML;
  }

  return escapeHtml(rawHtml);
}

/**
 * Focus trap utility for accessible modals and flyout drawers.
 */
let trappedElement = null;
let restoreFocusElement = null;

function handleFocusTrapKey(e) {
  if (!trappedElement) return;
  if (e.key !== 'Tab') return;

  const focusable = trappedElement.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  );
  if (focusable.length === 0) {
    e.preventDefault();
    return;
  }

  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (e.shiftKey) {
    if (document.activeElement === first) {
      last.focus();
      e.preventDefault();
    }
  } else {
    if (document.activeElement === last) {
      first.focus();
      e.preventDefault();
    }
  }
}

export function trapFocus(element) {
  restoreFocusElement = document.activeElement;
  trappedElement = element;
  document.addEventListener('keydown', handleFocusTrapKey);

  const focusable = element.querySelectorAll(
    'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
  );
  if (focusable.length > 0) {
    focusable[0].focus();
  }
}

export function releaseFocus() {
  document.removeEventListener('keydown', handleFocusTrapKey);
  trappedElement = null;
  if (restoreFocusElement && typeof restoreFocusElement.focus === 'function') {
    restoreFocusElement.focus();
  }
  restoreFocusElement = null;
}
