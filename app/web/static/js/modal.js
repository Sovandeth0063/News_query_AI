/**
 * Reader Modal Controller
 * Layout:
 *  - Sticky Header: [category badge] [source] · [time ago] ... [☆ Save] [✕ Close]
 *  - Scrolling Body:
 *      1. Title (22-24px, bold, max ~70ch, overflow safe)
 *      2. Key takeaway card (small label + AI note, semibold, accent border, tinted bg)
 *      3. Tag chips (click = close modal and filter feed)
 *      4. Summary (14-15px, 3 lines clamped + Show more toggle; hidden if empty or almost identical to title/takeaway)
 *      5. Also covered by (source chips linking to siblings, +N more if >3)
 *      6. Extracted text (collapsed accordion, lazy loaded, lightweight text button with chevron)
 *  - Sticky Footer: One primary button "Open original article ↗"
 *
 * Rules:
 *  - Uses the HTML `hidden` attribute for optional sections.
 *  - Text rendered with textContent only — zero innerHTML with raw text.
 *  - All URLs validated with isValidHttpUrl() before use.
 *  - ESC / backdrop-click / Close button all call closeModal().
 *  - Focus is moved to close button on open, trapped while open, returned on close.
 */

import { formatTimeAgo, isValidHttpUrl, trapFocus, releaseFocus } from './utils.js';
import { api } from './api.js';

let modalEl = null;
let currentArticle = null;
let onStateChangeCallback = null;

// Tracking state for lazy extracted text
let currentDetailPromise = null;
let currentArticleBody = null;
let isBodyRendered = false;

// ── Text-cleanup helpers (Display-time safety net) ───────────────────────────

/**
 * Decode common HTML entities safely (numeric and named).
 */
export function decodeEntities(str) {
  if (!str) return '';
  return str
    .replace(/&#(\d+);/g, (_, dec) => {
      const code = Number(dec);
      return (code > 0 && code < 65536) ? String.fromCharCode(code) : '';
    })
    .replace(/&#x([0-9a-fA-F]+);/g, (_, hex) => {
      const code = parseInt(hex, 16);
      return (code > 0 && code < 65536) ? String.fromCharCode(code) : '';
    })
    .replace(/&amp;/g,  '&')
    .replace(/&lt;/g,   '<')
    .replace(/&gt;/g,   '>')
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'")
    .replace(/&apos;/g, "'")
    .replace(/&nbsp;/g, ' ')
    .replace(/&mdash;/g, '—')
    .replace(/&ndash;/g, '–');
}

/**
 * Strip scraper noise:
 *  - "The post … appeared first on …" trailers
 *  - Trailing "[…]", "[...]", "[&#8230;]"
 *  - Trailing site name suffixes (" | SiteName", " – SiteName")
 */
export function cleanText(str) {
  if (!str) return '';
  let cleaned = decodeEntities(str);
  // Remove "The post ... appeared first on ..." trailer (case-insensitive)
  cleaned = cleaned.replace(/\s*The post .+? appeared first on .+\.?\s*$/i, '');
  // Strip trailing "[…]", "[...]", or ellipsis brackets
  cleaned = cleaned.replace(/\s*\[(?:…|\.\.\.|&#8230;|&#x2026;)\]\s*$/i, '');
  cleaned = cleaned.replace(/\s*\[\s*\.\.\.\s*\]\s*$/i, '');
  // Strip trailing " | SiteName" or " – SiteName" patterns from short fields
  cleaned = cleaned.replace(/\s*[\|–—]\s*[A-Za-z0-9 ]{2,40}$/, '');
  return cleaned.trim();
}

/**
 * Normalize string for similarity comparison:
 * lowercase, strip punctuation & non-alphanumeric, collapse whitespace.
 */
export function normalizeForCompare(str) {
  if (!str) return '';
  return cleanText(str)
    .toLowerCase()
    .replace(/[^\p{L}\p{N}\s]/gu, '')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Check if textA and textB are empty or almost identical.
 */
export function isAlmostIdentical(textA, textB) {
  const normA = normalizeForCompare(textA);
  const normB = normalizeForCompare(textB);
  if (!normA || !normB) return false;
  if (normA === normB) return true;

  const shorter = normA.length <= normB.length ? normA : normB;
  const longer  = normA.length > normB.length  ? normA : normB;

  // If shorter string is substantially contained within longer string (>75% length)
  if (longer.includes(shorter) && (shorter.length / longer.length) >= 0.75) {
    return true;
  }
  return false;
}

// ── Initialisation ─────────────────────────────────────────────────────────

export function initReaderModal(onStateChange) {
  modalEl = document.getElementById('readerModalBackdrop');
  onStateChangeCallback = onStateChange;
  if (!modalEl) return;

  // Close button
  document.getElementById('readerCloseBtn')?.addEventListener('click', closeModal);

  // Backdrop click
  modalEl.addEventListener('click', (e) => {
    if (e.target === modalEl) closeModal();
  });

  // ESC key
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalEl && !modalEl.hasAttribute('hidden') && modalEl.style.display !== 'none') {
      closeModal();
    }
  });

  // Header bookmark button
  document.getElementById('readerBookmarkBtn')?.addEventListener('click', async () => {
    if (!currentArticle) return;
    const next = !currentArticle.is_bookmarked;
    currentArticle.is_bookmarked = next ? 1 : 0;
    _updateBookmarkBtn(currentArticle.is_bookmarked);
    try {
      await api.setArticleBookmark(currentArticle.id, next);
      onStateChangeCallback?.(currentArticle.id, { is_bookmarked: currentArticle.is_bookmarked });
    } catch (err) {
      console.error('Bookmark toggle failed:', err);
    }
  });

  // Summary "Show more / Show less" toggle
  document.getElementById('readerSummaryToggle')?.addEventListener('click', () => {
    const summaryEl = document.getElementById('readerSummary');
    const toggleBtn = document.getElementById('readerSummaryToggle');
    if (!summaryEl || !toggleBtn) return;

    const expanded = toggleBtn.getAttribute('aria-expanded') === 'true';
    if (expanded) {
      summaryEl.classList.add('clamped');
      toggleBtn.textContent = 'Show more ▾';
      toggleBtn.setAttribute('aria-expanded', 'false');
    } else {
      summaryEl.classList.remove('clamped');
      toggleBtn.textContent = 'Show less ▴';
      toggleBtn.setAttribute('aria-expanded', 'true');
    }
  });

  // Extracted text accordion toggle listener (lazy loading)
  const fullBodyDetails = document.getElementById('readerFullBodyDetails');
  const fullBodySummary = document.getElementById('readerFullBodySummary');
  if (fullBodyDetails) {
    fullBodyDetails.addEventListener('toggle', () => {
      const isOpen = fullBodyDetails.open;
      fullBodySummary?.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      if (isOpen) {
        _handleAccordionOpened();
      }
    });
  }
}

// ── Bookmark button state ──────────────────────────────────────────────────

function _updateBookmarkBtn(isBookmarked) {
  const btn = document.getElementById('readerBookmarkBtn');
  if (!btn) return;
  const bookmarked = Boolean(isBookmarked);
  btn.setAttribute('aria-pressed', bookmarked ? 'true' : 'false');
  btn.setAttribute('aria-label', bookmarked ? 'Remove bookmark' : 'Save article');
  btn.title = bookmarked ? 'Remove bookmark' : 'Save article';
  btn.classList.toggle('bookmarked', bookmarked);
  const starSpan = btn.querySelector('.bookmark-star');
  if (starSpan) {
    starSpan.textContent = bookmarked ? '★' : '☆';
  } else {
    btn.textContent = bookmarked ? '★' : '☆';
  }
}

// ── Summary section update & overflow detection ────────────────────────────

function _renderSummarySection(titleText, takeawayText, summaryText) {
  const summarySec = document.getElementById('readerSummarySection');
  const summaryEl  = document.getElementById('readerSummary');
  const toggleBtn  = document.getElementById('readerSummaryToggle');
  if (!summarySec || !summaryEl) return;

  const cleanSummary = cleanText(summaryText || '');

  // Rule: Hide the whole section if it is empty or almost identical to title or takeaway
  if (!cleanSummary ||
      isAlmostIdentical(cleanSummary, titleText) ||
      (takeawayText && isAlmostIdentical(cleanSummary, takeawayText))) {
    summarySec.setAttribute('hidden', '');
    summaryEl.textContent = '';
    return;
  }

  summaryEl.textContent = cleanSummary;
  summaryEl.classList.add('clamped');
  summarySec.removeAttribute('hidden');

  if (toggleBtn) {
    toggleBtn.setAttribute('hidden', '');
    toggleBtn.textContent = 'Show more ▾';
    toggleBtn.setAttribute('aria-expanded', 'false');
  }

  requestAnimationFrame(() => {
    if (!toggleBtn) return;
    const overflows = summaryEl.scrollHeight > summaryEl.clientHeight + 2;
    if (overflows) {
      toggleBtn.removeAttribute('hidden');
    } else {
      toggleBtn.setAttribute('hidden', '');
    }
  });
}

// ── Tag chips rendering ────────────────────────────────────────────────────

function _renderTags(tags) {
  const tagsEl = document.getElementById('readerTags');
  if (!tagsEl) return;

  tagsEl.innerHTML = '';
  const tagList = Array.isArray(tags) ? tags.filter(Boolean) : [];
  if (tagList.length === 0) {
    tagsEl.setAttribute('hidden', '');
    return;
  }

  const searchInput = document.getElementById('globalSearchInput');

  tagList.forEach(t => {
    if (searchInput) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'reader-tag';
      btn.textContent = `#${t}`;
      btn.title = `Filter feed by #${t}`;
      btn.setAttribute('aria-label', `Filter feed by #${t}`);
      btn.addEventListener('click', () => {
        closeModal();
        searchInput.value = t;
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      });
      tagsEl.appendChild(btn);
    } else {
      const span = document.createElement('span');
      span.className = 'reader-tag';
      span.textContent = `#${t}`;
      tagsEl.appendChild(span);
    }
  });

  tagsEl.removeAttribute('hidden');
}

// ── Siblings rendering ─────────────────────────────────────────────────────

function _renderSiblings(siblings) {
  const siblingsBox = document.getElementById('readerSiblingsBox');
  const siblingsList = document.getElementById('readerSiblingsList');
  if (!siblingsBox || !siblingsList) return;

  siblingsList.innerHTML = '';
  if (!Array.isArray(siblings) || siblings.length === 0) {
    siblingsBox.setAttribute('hidden', '');
    return;
  }

  const maxVisible = 3;
  const initial = siblings.slice(0, maxVisible);
  const extra = siblings.slice(maxVisible);

  const createChip = (s) => {
    const chip = document.createElement('a');
    chip.className = 'sibling-chip';
    const validUrl = isValidHttpUrl(s.url);
    if (validUrl) {
      chip.href = s.url;
      chip.target = '_blank';
      chip.rel = 'noopener noreferrer';
    } else {
      chip.href = '#';
    }
    chip.textContent = `${s.source_name || 'Source'} ↗`;
    if (s.title) chip.title = cleanText(s.title);
    return chip;
  };

  initial.forEach(s => siblingsList.appendChild(createChip(s)));

  if (extra.length > 0) {
    const moreBtn = document.createElement('button');
    moreBtn.type = 'button';
    moreBtn.className = 'sibling-more-btn';
    moreBtn.textContent = `+${extra.length} more`;
    moreBtn.setAttribute('aria-label', `Show ${extra.length} more source links`);
    moreBtn.addEventListener('click', () => {
      moreBtn.remove();
      extra.forEach(s => siblingsList.appendChild(createChip(s)));
    });
    siblingsList.appendChild(moreBtn);
  }

  siblingsBox.removeAttribute('hidden');
}

// ── Accordion Lazy Loading ─────────────────────────────────────────────────

async function _handleAccordionOpened() {
  const fullBodyText = document.getElementById('readerFullBodyText');
  if (!fullBodyText || isBodyRendered) return;

  // Show loading skeleton while body is loading
  if (currentDetailPromise && currentArticleBody === null) {
    fullBodyText.innerHTML = `
      <div class="reader-body-skeleton" aria-busy="true">
        <div class="skeleton-line"></div>
        <div class="skeleton-line"></div>
        <div class="skeleton-line short"></div>
      </div>
    `;
    try {
      await currentDetailPromise;
    } catch (e) {
      // Ignored here; handled below
    }
  }

  _renderExtractedBody();
}

function _renderExtractedBody() {
  const fullBodyText = document.getElementById('readerFullBodyText');
  const fullBodyLabel = document.getElementById('readerFullBodyToggleText');
  if (!fullBodyText) return;

  isBodyRendered = true;
  fullBodyText.innerHTML = '';

  const bodyClean = cleanText(currentArticleBody || '');

  if (bodyClean) {
    const words = bodyClean.trim().split(/\s+/).filter(Boolean).length;
    if (fullBodyLabel) {
      fullBodyLabel.textContent = `Extracted text (${words.toLocaleString()} words)`;
    }

    const paragraphs = bodyClean.split(/\n{2,}|\n/).filter(p => p.trim().length > 0);
    paragraphs.forEach(pText => {
      const p = document.createElement('p');
      p.style.marginBottom = '1rem';
      p.textContent = pText.trim();
      fullBodyText.appendChild(p);
    });
  } else {
    // "If extracted text fails or is empty: show "Full text isn't available. Open the original article." inside the accordion, no error popups"
    if (fullBodyLabel) {
      fullBodyLabel.textContent = 'Extracted text';
    }

    const p = document.createElement('p');
    p.className = 'reader-body-fallback';
    p.textContent = "Full text isn't available. ";

    if (currentArticle && isValidHttpUrl(currentArticle.url)) {
      const a = document.createElement('a');
      a.href = currentArticle.url;
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      a.textContent = 'Open the original article ↗';
      p.appendChild(a);
    } else {
      p.textContent += 'Open the original article.';
    }

    fullBodyText.appendChild(p);
  }
}

// ── Open modal ─────────────────────────────────────────────────────────────

export async function openArticleModal(article) {
  if (!modalEl || !article) return;
  currentArticle = { ...article };

  // Reset lazy body tracking
  currentArticleBody = null;
  isBodyRendered = false;

  // Elements
  const titleEl         = document.getElementById('readerTitle');
  const sourceEl        = document.getElementById('readerSource');
  const dateEl          = document.getElementById('readerDate');
  const categoryEl      = document.getElementById('readerCategory');
  const takeawayBox     = document.getElementById('readerTakeawayContainer');
  const takeawayEl      = document.getElementById('readerTakeaway');
  const openOriginalBtn = document.getElementById('readerOpenOriginalBtn');
  const fullBodyBox     = document.getElementById('readerFullBodyContainer');
  const fullBodyDetails = document.getElementById('readerFullBodyDetails');
  const fullBodyLabel   = document.getElementById('readerFullBodyToggleText');
  const fullBodyText    = document.getElementById('readerFullBodyText');
  const siblingsBox     = document.getElementById('readerSiblingsBox');

  // ── 1. Header Metadata ───────────────────────────────────────────────────
  const cleanTitle = cleanText(currentArticle.title) || 'Untitled Article';
  if (titleEl) titleEl.textContent = cleanTitle;

  if (categoryEl) {
    categoryEl.textContent = currentArticle.category || 'TECH';
    categoryEl.className = 'badge';
    if (currentArticle.category === 'AI_LLM') categoryEl.classList.add('badge-ai');
    else if (currentArticle.category === 'DATA_SCIENCE_ML') categoryEl.classList.add('badge-ds');
    else if (currentArticle.category === 'AI_RESEARCH') categoryEl.classList.add('badge-paper');
    else categoryEl.classList.add('badge-tech');
  }

  if (sourceEl) {
    sourceEl.textContent = currentArticle.source_name || 'Source';
  }

  if (dateEl) {
    dateEl.textContent = formatTimeAgo(currentArticle.published_at_utc);
    // Tooltip with full ISO / local date
    const fullDate = currentArticle.published_at_utc
      ? new Date(currentArticle.published_at_utc).toLocaleString(undefined, { dateStyle: 'full', timeStyle: 'short' })
      : '';
    dateEl.title = fullDate;
  }

  // Header Bookmark button
  _updateBookmarkBtn(currentArticle.is_bookmarked);

  // ── 2. Key Takeaway ──────────────────────────────────────────────────────
  const rawTakeaway = cleanText(currentArticle.takeaway || '');
  if (takeawayBox && takeawayEl) {
    if (rawTakeaway) {
      takeawayEl.textContent = rawTakeaway;
      takeawayBox.removeAttribute('hidden');
    } else {
      takeawayEl.textContent = '';
      takeawayBox.setAttribute('hidden', '');
    }
  }

  // ── 3. Tag Chips ─────────────────────────────────────────────────────────
  _renderTags(currentArticle.tags);

  // ── 4. Summary ───────────────────────────────────────────────────────────
  _renderSummarySection(cleanTitle, rawTakeaway, currentArticle.summary);

  // ── 5. Siblings (hidden until API returns) ────────────────────────────────
  if (siblingsBox) siblingsBox.setAttribute('hidden', '');

  // ── 6. Extracted Text Accordion (closed by default) ───────────────────────
  if (fullBodyBox) fullBodyBox.removeAttribute('hidden');
  if (fullBodyDetails) {
    fullBodyDetails.removeAttribute('open');
    document.getElementById('readerFullBodySummary')?.setAttribute('aria-expanded', 'false');
  }
  if (fullBodyLabel) fullBodyLabel.textContent = 'Extracted text';
  if (fullBodyText) fullBodyText.innerHTML = '';

  // ── Sticky Footer: Open Original ─────────────────────────────────────────
  if (openOriginalBtn) {
    if (isValidHttpUrl(currentArticle.url)) {
      openOriginalBtn.href = currentArticle.url;
      openOriginalBtn.style.display = '';
    } else {
      openOriginalBtn.removeAttribute('href');
      openOriginalBtn.style.display = 'none';
    }
  }

  // ── Show modal, lock body scroll, trap focus ──────────────────────────────
  modalEl.style.display = 'flex';
  modalEl.removeAttribute('aria-hidden');
  document.body.style.overflow = 'hidden';

  // Accessibility: focus moves to the close button on open
  trapFocus(modalEl.querySelector('.reader-modal-dialog') || modalEl);
  document.getElementById('readerCloseBtn')?.focus();

  // ── Mark as read ─────────────────────────────────────────────────────────
  if (!currentArticle.is_read) {
    currentArticle.is_read = 1;
    api.setArticleRead(currentArticle.id, true).catch(() => {});
    onStateChangeCallback?.(currentArticle.id, { is_read: 1 });
  }

  // ── Async Detail Fetch (Updated takeaway, tags, summary, siblings, body) ──
  currentDetailPromise = api.getArticleDetail(currentArticle.id)
    .then(detail => {
      if (!detail || !currentArticle || currentArticle.id !== article.id) return detail;

      if (detail.article) {
        const art = detail.article;

        // Takeaway update
        const liveTakeaway = cleanText(art.takeaway || '');
        if (takeawayBox && takeawayEl) {
          if (liveTakeaway) {
            takeawayEl.textContent = liveTakeaway;
            takeawayBox.removeAttribute('hidden');
          } else if (!rawTakeaway) {
            takeawayBox.setAttribute('hidden', '');
          }
        }

        // Tags update
        if (Array.isArray(art.tags) && art.tags.length > 0) {
          _renderTags(art.tags);
        }

        // Summary update
        _renderSummarySection(cleanTitle, liveTakeaway || rawTakeaway, art.summary || currentArticle.summary);

        // Body text update
        currentArticleBody = art.body || '';
        if (currentArticleBody.trim() && fullBodyLabel) {
          const words = currentArticleBody.trim().split(/\s+/).filter(Boolean).length;
          fullBodyLabel.textContent = `Extracted text (${words.toLocaleString()} words)`;
        }

        // If user already opened the accordion before fetch finished
        if (fullBodyDetails && fullBodyDetails.open && !isBodyRendered) {
          _renderExtractedBody();
        }
      }

      // Siblings update
      if (detail.siblings) {
        _renderSiblings(detail.siblings);
      }

      return detail;
    })
    .catch(err => {
      console.warn('Article detail fetch failed:', err);
      currentArticleBody = '';
      if (fullBodyDetails && fullBodyDetails.open && !isBodyRendered) {
        _renderExtractedBody();
      }
    });
}

// ── Close modal ────────────────────────────────────────────────────────────

export function closeModal() {
  if (!modalEl) return;
  modalEl.style.display = 'none';
  modalEl.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
  releaseFocus();
  currentArticle = null;
  currentDetailPromise = null;
  currentArticleBody = null;
  isBodyRendered = false;
}
