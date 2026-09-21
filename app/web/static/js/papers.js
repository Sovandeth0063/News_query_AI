/**
 * Papers Controller: arXiv Research Papers with Expandable Abstracts,
 * Server Search, and Load More Pagination.
 */

import { api } from './api.js';
import { escapeHtml, formatTimeAgo, isValidHttpUrl, debounce } from './utils.js';
import { showToast } from './toast.js';

const PAGE_SIZE = 30;

let loadedPapers = [];
let loadedIds = new Set();
let currentSearch = '';
let hasMore = true;
let isLoading = false;
let abortCtrl = null;
let initialized = false;

export function initPapers() {
  if (initialized) return;
  initialized = true;

  bindEvents();
  loadPapers(true);
}

function bindEvents() {
  const searchInput = document.getElementById('papersSearchInput');
  const clearBtn = document.getElementById('papersSearchClearBtn');

  if (searchInput) {
    const debouncedSearch = debounce(() => {
      currentSearch = searchInput.value.trim();
      if (clearBtn) clearBtn.style.display = currentSearch ? 'inline-flex' : 'none';
      loadPapers(true);
    }, 300);

    searchInput.addEventListener('input', debouncedSearch);
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      clearBtn.style.display = 'none';
      currentSearch = '';
      loadPapers(true);
      if (searchInput) searchInput.focus();
    });
  }

  const loadMoreBtn = document.getElementById('papersLoadMoreBtn');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', () => {
      if (!isLoading && hasMore) {
        loadPapers(false);
      }
    });
  }
}

export async function loadPapers(reset = false) {
  if (isLoading && abortCtrl) {
    abortCtrl.abort();
  }

  isLoading = true;
  abortCtrl = new AbortController();

  const listEl = document.getElementById('papersList');
  const loadMoreContainer = document.getElementById('papersLoadMoreContainer');
  const countBadge = document.getElementById('papersCountBadge');

  if (reset) {
    loadedPapers = [];
    loadedIds.clear();
    hasMore = true;
    renderSkeleton(listEl);
  }

  const offset = loadedPapers.length;

  try {
    const data = await api.getPapers({
      search: currentSearch,
      limit: PAGE_SIZE,
      offset,
      signal: abortCtrl.signal
    });

    const incoming = data.papers || [];

    // Client-side deduplication
    let newUnique = [];
    for (const item of incoming) {
      if (!loadedIds.has(item.id)) {
        loadedIds.add(item.id);
        newUnique.push(item);
      }
    }

    if (reset) {
      loadedPapers = newUnique;
    } else {
      loadedPapers = loadedPapers.concat(newUnique);
    }

    hasMore = incoming.length >= PAGE_SIZE;

    if (countBadge) {
      countBadge.textContent = `${loadedPapers.length} papers`;
    }

    renderPaperRows();

    if (loadMoreContainer) {
      loadMoreContainer.style.display = hasMore ? 'block' : 'none';
    }

  } catch (err) {
    if (err.name === 'AbortError') return;
    renderError(listEl, err.message, () => loadPapers(reset));
  } finally {
    isLoading = false;
  }
}

function renderPaperRows() {
  const listEl = document.getElementById('papersList');
  if (!listEl) return;

  if (loadedPapers.length === 0) {
    renderEmpty(listEl);
    return;
  }

  listEl.innerHTML = loadedPapers.map(renderPaperRow).join('');

  // Attach accordion and bookmark listeners
  loadedPapers.forEach(paper => {
    const rowEl = document.getElementById(`paper-${paper.id}`);
    if (!rowEl) return;

    // Abstract toggle
    const toggleBtn = rowEl.querySelector('.paper-expand-btn');
    const abstractBox = rowEl.querySelector('.paper-abstract-box');
    if (toggleBtn && abstractBox) {
      toggleBtn.addEventListener('click', () => {
        const isExpanded = abstractBox.classList.toggle('expanded');
        toggleBtn.setAttribute('aria-expanded', isExpanded ? 'true' : 'false');
        toggleBtn.textContent = isExpanded ? '▲ Hide abstract' : '▼ View abstract';
      });
    }

    // Bookmark toggle
    const bkmkBtn = rowEl.querySelector('.btn-bookmark-paper');
    if (bkmkBtn) {
      bkmkBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const nextState = !paper.is_bookmarked;
        paper.is_bookmarked = nextState ? 1 : 0;
        bkmkBtn.classList.toggle('active', nextState);
        bkmkBtn.setAttribute('aria-pressed', nextState ? 'true' : 'false');
        bkmkBtn.innerHTML = nextState ? '★' : '☆';
        showToast(nextState ? 'Paper bookmarked' : 'Bookmark removed', 'info', 2000);
        try {
          await api.setArticleBookmark(paper.id, nextState);
        } catch (err) {
          console.error('Bookmark error:', err);
        }
      });
    }
  });
}

function renderPaperRow(p) {
  const isBookmarked = Boolean(p.is_bookmarked);
  const timeAgo = formatTimeAgo(p.published_at_utc);
  const safeUrl = isValidHttpUrl(p.url) ? p.url : '#';

  // Category tags (tags or cs.AI default)
  const tags = Array.isArray(p.tags) && p.tags.length > 0 ? p.tags : ['arXiv:AI'];
  const tagChips = tags.slice(0, 2).map(t => `<span class="paper-cat-chip">${escapeHtml(t)}</span>`).join('');

  return `
    <div class="paper-row" id="paper-${p.id}">
      <div class="paper-main-content">
        <div class="paper-meta-top">
          ${tagChips}
          <span class="paper-time">${timeAgo}</span>
        </div>
        <h4 class="paper-title">
          <a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(p.title)}
          </a>
        </h4>
        <div class="paper-actions-bar">
          <button class="paper-expand-btn" aria-expanded="false" aria-controls="abstract-${p.id}">
            ▼ View abstract
          </button>
          <a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="paper-arxiv-link">
            arXiv ↗
          </a>
        </div>
        <div class="paper-abstract-box" id="abstract-${p.id}">
          <p>${escapeHtml(p.summary || 'No abstract summary available.')}</p>
        </div>
      </div>
      <div class="paper-side-action">
        <button class="btn-icon btn-bookmark-paper ${isBookmarked ? 'active' : ''}" 
                aria-label="${isBookmarked ? 'Remove bookmark' : 'Bookmark paper'}"
                aria-pressed="${isBookmarked ? 'true' : 'false'}"
                title="${isBookmarked ? 'Remove bookmark' : 'Bookmark paper'}">
          ${isBookmarked ? '★' : '☆'}
        </button>
      </div>
    </div>
  `;
}

function renderSkeleton(container) {
  if (!container) return;
  container.innerHTML = `
    <div class="skeleton-card" style="margin-bottom: 12px;">
      <div class="skeleton-meta"></div>
      <div class="skeleton-title" style="width: 70%;"></div>
    </div>
    <div class="skeleton-card" style="margin-bottom: 12px;">
      <div class="skeleton-meta"></div>
      <div class="skeleton-title" style="width: 80%;"></div>
    </div>
    <div class="skeleton-card">
      <div class="skeleton-meta"></div>
      <div class="skeleton-title" style="width: 65%;"></div>
    </div>
  `;
}

function renderEmpty(container) {
  if (!container) return;
  container.innerHTML = `
    <div class="feed-empty-state">
      <div class="empty-icon">🔬</div>
      <h4>No research papers found</h4>
      <p>${currentSearch ? `No papers matching "${escapeHtml(currentSearch)}".` : 'No papers available in the feed right now.'}</p>
    </div>
  `;
}

function renderError(container, message, retryFn) {
  if (!container) return;
  container.innerHTML = `
    <div class="feed-error-state">
      <div class="error-icon">⚠️</div>
      <h4>Unable to load papers</h4>
      <p>${escapeHtml(message)}</p>
      <button class="btn btn-primary btn-retry-papers">Retry</button>
    </div>
  `;
  const btn = container.querySelector('.btn-retry-papers');
  if (btn) btn.addEventListener('click', retryFn);
}
