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
  const summaryEl = document.getElementById('readerSummary');
  const tagsEl = document.getElementById('readerTags');
  const siblingsBox = document.getElementById('readerSiblingsBox');
  const siblingsList = document.getElementById('readerSiblingsList');
  const openOriginalBtn = document.getElementById('readerOpenOriginalBtn');

  // Populate basic metadata immediately
  titleEl.textContent = currentArticle.title || 'Untitled Article';
  sourceEl.textContent = currentArticle.source_name || 'Source';
  dateEl.textContent = formatTimeAgo(currentArticle.published_at_utc);
  categoryEl.textContent = currentArticle.category || 'TECH';
  summaryEl.textContent = currentArticle.summary || 'No summary preview available.';

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

  // Fetch sibling coverage if clustered
  try {
    const detail = await api.getArticleDetail(currentArticle.id);
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
    // Non-critical: siblings failed to load
  }
}

export function closeModal() {
  if (!modalEl) return;
  modalEl.style.display = 'none';
  document.body.style.overflow = '';
  releaseFocus();
  currentArticle = null;
}
