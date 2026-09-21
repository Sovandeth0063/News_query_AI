/**
 * Reader Modal Controller: Displays snippet, tags, cluster coverage, and external link.
 * Focus-trapped and accessible.
 */

import { escapeHtml, formatTimeAgo, isValidHttpUrl, trapFocus, releaseFocus } from './utils.js';
import { api } from './api.js';

let modalEl = null;
let currentArticle = null;
let onStateChangeCallback = null;

export function initReaderModal(onStateChange) {
  modalEl = document.getElementById('readerModalBackdrop');
  onStateChangeCallback = onStateChange;
  if (!modalEl) return;

  const closeBtn = document.getElementById('readerCloseBtn');
  if (closeBtn) {
    closeBtn.addEventListener('click', closeModal);
  }

  modalEl.addEventListener('click', (e) => {
    if (e.target === modalEl) {
      closeModal();
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modalEl && modalEl.style.display !== 'none') {
      closeModal();
    }
  });

  const bkmkBtn = document.getElementById('readerBookmarkBtn');
  if (bkmkBtn) {
    bkmkBtn.addEventListener('click', async () => {
      if (!currentArticle) return;
      const nextBkmk = !currentArticle.is_bookmarked;
      currentArticle.is_bookmarked = nextBkmk ? 1 : 0;
      updateBookmarkButton(currentArticle.is_bookmarked);
      try {
        await api.setArticleBookmark(currentArticle.id, nextBkmk);
        if (typeof onStateChangeCallback === 'function') {
          onStateChangeCallback(currentArticle.id, { is_bookmarked: currentArticle.is_bookmarked });
        }
      } catch (e) {
        console.error('Error toggling bookmark:', e);
      }
    });
  }
}

function updateBookmarkButton(isBookmarked) {
  const bkmkBtn = document.getElementById('readerBookmarkBtn');
  if (bkmkBtn) {
    bkmkBtn.setAttribute('aria-pressed', isBookmarked ? 'true' : 'false');
    bkmkBtn.classList.toggle('active', Boolean(isBookmarked));
    bkmkBtn.innerHTML = isBookmarked ? '★ Saved' : '☆ Save';
  }
}

export async function openArticleModal(article) {
  if (!modalEl || !article) return;
  currentArticle = { ...article };

  const titleEl = document.getElementById('readerTitle');
  const sourceEl = document.getElementById('readerSource');
  const dateEl = document.getElementById('readerDate');
  const categoryEl = document.getElementById('readerCategory');
  const takeawayContainer = document.getElementById('readerTakeawayContainer');
  const takeawayEl = document.getElementById('readerTakeaway');
  const summaryEl = document.getElementById('readerSummary');
  const fullBodyContainer = document.getElementById('readerFullBodyContainer');
  const fullBodyText = document.getElementById('readerFullBodyText');
  const fullBodyToggleText = document.getElementById('readerFullBodyToggleText');
  const tagsEl = document.getElementById('readerTags');
  const siblingsBox = document.getElementById('readerSiblingsBox');
  const siblingsList = document.getElementById('readerSiblingsList');
  const openOriginalBtn = document.getElementById('readerOpenOriginalBtn');

  // Populate basic metadata immediately
  titleEl.textContent = currentArticle.title || 'Untitled Article';
  sourceEl.textContent = currentArticle.source_name || 'Source';
  dateEl.textContent = formatTimeAgo(currentArticle.published_at_utc);
  categoryEl.textContent = currentArticle.category || 'TECH';

  // Populate Key Takeaway immediately if present
  const initialTakeaway = (currentArticle.takeaway || '').trim();
  if (takeawayContainer && takeawayEl) {
    if (initialTakeaway) {
      takeawayEl.textContent = initialTakeaway;
      takeawayContainer.style.display = 'block';
    } else {
      takeawayContainer.style.display = 'none';
    }
  }

  // Populate Summary
  summaryEl.textContent = currentArticle.summary || 'No summary preview available.';

  // Reset full body container
  if (fullBodyContainer) fullBodyContainer.style.display = 'none';
  if (fullBodyText) fullBodyText.textContent = '';

  // External URL
  if (isValidHttpUrl(currentArticle.url)) {
    openOriginalBtn.href = currentArticle.url;
    openOriginalBtn.style.display = 'inline-flex';
  } else {
    openOriginalBtn.style.display = 'none';
  }

  // Tags
  tagsEl.innerHTML = '';
  if (Array.isArray(currentArticle.tags) && currentArticle.tags.length > 0) {
    tagsEl.innerHTML = currentArticle.tags.map(t => `<span class="reader-tag">#${escapeHtml(t)}</span>`).join('');
  }

  // Bookmark button
  updateBookmarkButton(currentArticle.is_bookmarked);

  // Siblings container reset
  siblingsBox.style.display = 'none';
  siblingsList.innerHTML = '';

  // Show modal
  modalEl.style.display = 'flex';
  document.body.style.overflow = 'hidden';
  trapFocus(modalEl.querySelector('.reader-modal-dialog') || modalEl);

  // Mark read locally and in backend
  if (!currentArticle.is_read) {
    currentArticle.is_read = 1;
    api.setArticleRead(currentArticle.id, true).catch(() => {});
    if (typeof onStateChangeCallback === 'function') {
      onStateChangeCallback(currentArticle.id, { is_read: 1 });
    }
  }

  // Fetch full details (full body, updated takeaway, and cluster siblings)
  try {
    const detail = await api.getArticleDetail(currentArticle.id);
    if (detail && detail.article) {
      const art = detail.article;

      // Update Key Takeaway if received from database
      const liveTakeaway = (art.takeaway || currentArticle.takeaway || '').trim();
      if (takeawayContainer && takeawayEl) {
        if (liveTakeaway) {
          takeawayEl.textContent = liveTakeaway;
          takeawayContainer.style.display = 'block';
        } else if (art.summary) {
          // Generate fallback takeaway from first sentence of summary
          const firstSentence = art.summary.split(/\.\s+/)[0].trim();
          takeawayEl.textContent = firstSentence.endsWith('.') ? firstSentence : firstSentence + '.';
          takeawayContainer.style.display = 'block';
        }
      }

      // Update Summary if returned
      if (art.summary) {
        summaryEl.textContent = art.summary;
      }

      // Full ingested body text (collapsible toggle)
      if (art.body && art.body.trim() && art.body.length > (art.summary || '').length + 60) {
        if (fullBodyContainer && fullBodyText) {
          fullBodyContainer.style.display = 'block';
          fullBodyText.textContent = art.body;
          const words = art.body.trim().split(/\s+/).length;
          if (fullBodyToggleText) {
            fullBodyToggleText.textContent = `Read Full Extracted Article (${words} words)`;
          }
        }
      }

      // Tags
      if (Array.isArray(art.tags) && art.tags.length > 0) {
        tagsEl.innerHTML = art.tags.map(t => `<span class="reader-tag">#${escapeHtml(t)}</span>`).join('');
      }
    }

    if (detail && detail.siblings && detail.siblings.length > 0) {
      siblingsBox.style.display = 'block';
      siblingsList.innerHTML = detail.siblings.map(s => {
        const urlValid = isValidHttpUrl(s.url);
        return `
          <li class="sibling-item">
            ${urlValid 
              ? `<a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(s.title)}</a>` 
              : `<span>${escapeHtml(s.title)}</span>`}
            <span class="sibling-source">${escapeHtml(s.source_name || 'Source')}</span>
          </li>
        `;
      }).join('');
    }
  } catch (e) {
    // Non-critical: siblings or full body failed to load
  }
}

export function closeModal() {
  if (!modalEl) return;
  modalEl.style.display = 'none';
  document.body.style.overflow = '';
  releaseFocus();
  currentArticle = null;
}
