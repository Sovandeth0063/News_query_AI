/**
 * Feed Controller: Category Filtering, Server-Side Search,
 * Client ID Deduplication, Date Bucket Grouping, Compact Density Mode,
 * and Refined Knowledge Card Hierarchy.
 */

import { api } from './api.js';
import { escapeHtml, formatTimeAgo, isValidHttpUrl, isValidArticle, debounce } from './utils.js';
import { openArticleModal } from './modal.js';
import { showToast } from './toast.js';

const PAGE_SIZE = 40;

let currentCategory = 'ALL';
let currentSearch = '';
let currentSort = 'score'; // 'score' | 'date'
let loadedArticles = [];
let loadedIds = new Set();
let hasMore = true;
let isLoading = false;
let abortCtrl = null;

export function initFeed() {
  bindEvents();
  initDensity();
  loadFeed(true);
}

function bindEvents() {
  // Category pills
  const pills = document.querySelectorAll('.feed-filter-pill');
  pills.forEach(pill => {
    pill.addEventListener('click', () => {
      pills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      currentCategory = pill.dataset.category || 'ALL';
      loadFeed(true);
    });
  });

  // Sort dropdown
  const sortSelect = document.getElementById('feedSortSelect');
  if (sortSelect) {
    sortSelect.addEventListener('change', (e) => {
      currentSort = e.target.value;
      loadFeed(true);
    });
  }

  // Search input with 300ms debounce
  const searchInput = document.getElementById('globalSearchInput');
  const clearBtn = document.getElementById('searchClearBtn');

  if (searchInput) {
    const debouncedSearch = debounce(() => {
      currentSearch = searchInput.value.trim();
      if (clearBtn) clearBtn.style.display = currentSearch ? 'inline-flex' : 'none';
      loadFeed(true);
    }, 300);

    searchInput.addEventListener('input', debouncedSearch);

    // Keyboard shortcut "/" to focus search
    document.addEventListener('keydown', (e) => {
      if (e.key === '/' && document.activeElement !== searchInput && 
          document.activeElement.tagName !== 'INPUT' && 
          document.activeElement.tagName !== 'TEXTAREA') {
        e.preventDefault();
        searchInput.focus();
        searchInput.select();
      }
    });
  }

  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      if (searchInput) searchInput.value = '';
      clearBtn.style.display = 'none';
      currentSearch = '';
      loadFeed(true);
      if (searchInput) searchInput.focus();
    });
  }

  // Load More button
  const loadMoreBtn = document.getElementById('feedLoadMoreBtn');
  if (loadMoreBtn) {
    loadMoreBtn.addEventListener('click', () => {
      if (!isLoading && hasMore) {
        loadFeed(false);
      }
    });
  }
}

export function initDensity() {
  const isCompact = localStorage.getItem('newsquery_density') === 'compact';
  applyDensity(isCompact);

  const densityBtn = document.getElementById('densityToggleBtn');
  if (densityBtn) {
    densityBtn.addEventListener('click', () => {
      const current = document.body.classList.contains('compact-mode');
      const next = !current;
      applyDensity(next);
      localStorage.setItem('newsquery_density', next ? 'compact' : 'comfortable');
      showToast(next ? 'Compact density enabled' : 'Comfortable density enabled', 'info', 1500);
    });
  }

  // Keyboard shortcut 'D' to toggle density
  document.addEventListener('keydown', (e) => {
    if ((e.key === 'd' || e.key === 'D') && 
        document.activeElement.tagName !== 'INPUT' && 
        document.activeElement.tagName !== 'TEXTAREA') {
      const current = document.body.classList.contains('compact-mode');
      const next = !current;
      applyDensity(next);
      localStorage.setItem('newsquery_density', next ? 'compact' : 'comfortable');
      showToast(next ? 'Compact density enabled' : 'Comfortable density enabled', 'info', 1500);
    }
  });
}

function applyDensity(isCompact) {
  document.body.classList.toggle('compact-mode', isCompact);
  const densityBtn = document.getElementById('densityToggleBtn');
  if (densityBtn) {
    densityBtn.setAttribute('aria-pressed', isCompact ? 'true' : 'false');
    densityBtn.title = isCompact ? 'Switch to comfortable density (D)' : 'Switch to compact density (D)';
    densityBtn.classList.toggle('active', isCompact);
  }
}

export async function loadFeed(reset = false) {
  if (isLoading) {
    if (abortCtrl) abortCtrl.abort();
  }

  isLoading = true;
  abortCtrl = new AbortController();

  const listEl = document.getElementById('feedArticleList');
  const loadMoreContainer = document.getElementById('feedLoadMoreContainer');
  const countBadge = document.getElementById('feedCountBadge');

  if (reset) {
    loadedArticles = [];
    loadedIds.clear();
    hasMore = true;
    renderSkeleton(listEl);
  }

  const offset = loadedArticles.length;

  try {
    const data = await api.getFeed({
      category: currentCategory,
      search: currentSearch,
      sort: currentSort,
      limit: PAGE_SIZE,
      offset,
      signal: abortCtrl.signal
    });

    const incoming = (data.articles || []).filter(isValidArticle);

    // Client-side deduplication against already loaded IDs
    let newUniqueItems = [];
    for (const item of incoming) {
      if (!loadedIds.has(item.id)) {
        loadedIds.add(item.id);
        newUniqueItems.push(item);
      }
    }

    if (reset) {
      loadedArticles = newUniqueItems;
    } else {
      loadedArticles = loadedArticles.concat(newUniqueItems);
    }

    hasMore = incoming.length >= PAGE_SIZE;

    // Update status badge
    if (countBadge) {
      countBadge.textContent = `${loadedArticles.length} stories`;
    }

    sortAndRenderArticles();

    // Toggle Load More button visibility
    if (loadMoreContainer) {
      loadMoreContainer.style.display = hasMore ? 'block' : 'none';
    }

  } catch (err) {
    if (err.name === 'AbortError') return;
    renderError(listEl, err.message, () => loadFeed(reset));
  } finally {
    isLoading = false;
  }
}

function getDateBucket(isoStr) {
  if (!isoStr) return 'Earlier';
  try {
    const d = new Date(isoStr);
    const now = new Date();
    const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
    const itemDay = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diffMs = today.getTime() - itemDay.getTime();
    const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
    if (diffDays <= 0) return 'Today';
    if (diffDays === 1) return 'Yesterday';
    return 'Earlier';
  } catch (e) {
    return 'Earlier';
  }
}

function sortAndRenderArticles() {
  const listEl = document.getElementById('feedArticleList');
  if (!listEl) return;

  if (loadedArticles.length === 0) {
    renderEmpty(listEl);
    return;
  }

  // Client sort
  const sorted = [...loadedArticles];
  if (currentSort === 'date') {
    sorted.sort((a, b) => new Date(b.published_at_utc || 0) - new Date(a.published_at_utc || 0));
  } else {
    sorted.sort((a, b) => (b.score_cached || 0) - (a.score_cached || 0) || 
      new Date(b.published_at_utc || 0) - new Date(a.published_at_utc || 0));
  }

  // Group into Date Buckets (Today, Yesterday, Earlier)
  const buckets = { 'Today': [], 'Yesterday': [], 'Earlier': [] };
  sorted.forEach(a => {
    const b = getDateBucket(a.published_at_utc);
    buckets[b].push(a);
  });

  let html = '';
  ['Today', 'Yesterday', 'Earlier'].forEach(bucketName => {
    const items = buckets[bucketName];
    if (items && items.length > 0) {
      html += `
        <div class="date-group-header">
          <span class="date-group-title">${bucketName}</span>
          <span class="date-group-count">(${items.length})</span>
        </div>
      `;
      html += items.map(renderArticleCard).join('');
    }
  });

  listEl.innerHTML = html;

  // Attach card event listeners
  sorted.forEach(article => {
    const cardEl = document.getElementById(`card-${article.id}`);
    if (!cardEl) return;

    // Snippet preview click
    const previewBtn = cardEl.querySelector('.btn-preview');
    if (previewBtn) {
      previewBtn.addEventListener('click', (e) => {
        e.preventDefault();
        openArticleModal(article);
      });
    }

    // Bookmark toggle
    const bkmkBtn = cardEl.querySelector('.btn-bookmark-card');
    if (bkmkBtn) {
      bkmkBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const nextState = !article.is_bookmarked;
        article.is_bookmarked = nextState ? 1 : 0;
        bkmkBtn.classList.toggle('active', nextState);
        bkmkBtn.setAttribute('aria-pressed', nextState ? 'true' : 'false');
        bkmkBtn.innerHTML = nextState ? '★' : '☆';
        showToast(nextState ? 'Article bookmarked' : 'Bookmark removed', 'info', 2000);
        try {
          await api.setArticleBookmark(article.id, nextState);
        } catch (err) {
          console.error('Bookmark error:', err);
        }
      });
    }

    // Read toggle
    const readBtn = cardEl.querySelector('.btn-read-card');
    if (readBtn) {
      readBtn.addEventListener('click', async (e) => {
        e.stopPropagation();
        const nextState = !article.is_read;
        article.is_read = nextState ? 1 : 0;
        cardEl.classList.toggle('is-read', nextState);
        const newDot = cardEl.querySelector('.new-dot');
        if (newDot) newDot.style.display = nextState ? 'none' : 'inline-block';
        try {
          await api.setArticleRead(article.id, nextState);
        } catch (err) {
          console.error('Read toggle error:', err);
        }
      });
    }
  });

  // Attach tag chips click listeners
  listEl.querySelectorAll('.tag-chip').forEach(chip => {
    chip.addEventListener('click', (e) => {
      e.stopPropagation();
      const tag = chip.dataset.tag;
      const searchInput = document.getElementById('globalSearchInput');
      if (searchInput && tag) {
        searchInput.value = tag;
        searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      }
    });
  });
}

function renderArticleCard(a) {
  const isRead = Boolean(a.is_read);
  const isBookmarked = Boolean(a.is_bookmarked);
  const timeAgo = formatTimeAgo(a.published_at_utc);

  // Category badge class
  let badgeClass = 'badge-tech';
  let badgeLabel = 'Tech';
  if (a.category === 'AI_LLM') {
    badgeClass = 'badge-ai';
    badgeLabel = 'AI / LLM';
  } else if (a.category === 'DATA_SCIENCE_ML') {
    badgeClass = 'badge-ds';
    badgeLabel = 'Data Science';
  } else if (a.category === 'DATA_ENG_CLOUD') {
    badgeClass = 'badge-dataeng';
    badgeLabel = 'Data Eng / Cloud';
  }

  // Cluster tag
  const clusterTag = (a.cluster_size && a.cluster_size > 1)
    ? `<span class="cluster-badge" title="Also covered across ${a.cluster_size} sources">⚡ ${a.cluster_size} sources</span>`
    : '';

  const safeUrl = isValidHttpUrl(a.url) ? a.url : '#';
  const displayTakeaway = a.takeaway || a.summary || '';

  // Tags chips
  const tagsList = (a.tags || []).slice(0, 3);
  const tagsHtml = tagsList.map(t => 
    `<button class="tag-chip" data-tag="${escapeHtml(t)}" title="Filter by #${escapeHtml(t)}">#${escapeHtml(t)}</button>`
  ).join(' ');

  let eventBadge = '';
  if (a.event_type === 'model_release') {
    eventBadge = `<span class="badge badge-release" title="Newly launched model">🚀 Launch</span>`;
  } else if (a.event_type === 'model_update') {
    eventBadge = `<span class="badge badge-update" title="Model update">🔄 Update</span>`;
  }

  return `
    <article class="article-card ${isRead ? 'is-read' : ''}" id="card-${a.id}">
      <div class="card-header">
        <div class="card-meta">
          ${!isRead ? '<span class="new-dot" title="New unread story" aria-label="New unread story"></span>' : ''}
          <span class="badge ${badgeClass}">${badgeLabel}</span>
          ${eventBadge}
          <span class="source-name">${escapeHtml(a.source_name || 'Source')}</span>
          ${clusterTag}
          <span class="time-ago">${timeAgo}</span>
        </div>
        <div class="card-actions-quick">
          <button class="btn-icon btn-bookmark-card ${isBookmarked ? 'active' : ''}" 
                  aria-label="${isBookmarked ? 'Remove bookmark' : 'Bookmark story'}"
                  aria-pressed="${isBookmarked ? 'true' : 'false'}"
                  title="${isBookmarked ? 'Remove bookmark' : 'Bookmark story'}">
            ${isBookmarked ? '★' : '☆'}
          </button>
          <button class="btn-icon btn-read-card" 
                  aria-label="${isRead ? 'Mark unread' : 'Mark as read'}" 
                  title="${isRead ? 'Mark unread' : 'Mark as read'}">
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="20 6 9 17 4 12"></polyline></svg>
          </button>
        </div>
      </div>

      <h3 class="card-title">
        <a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="title-link">
          ${escapeHtml(a.title)}
        </a>
      </h3>

      <p class="card-takeaway">
        ${escapeHtml(displayTakeaway)}
      </p>

      <div class="card-footer-meta">
        <div class="card-tags-row">
          ${tagsHtml}
        </div>
        <button class="btn-preview" aria-label="Preview story details and sources">
          Preview snippet →
        </button>
      </div>
    </article>
  `;
}

function renderSkeleton(container) {
  if (!container) return;
  container.innerHTML = `
    <div class="skeleton-card">
      <div class="skeleton-meta"></div>
      <div class="skeleton-title"></div>
      <div class="skeleton-line" style="width: 90%;"></div>
      <div class="skeleton-line" style="width: 75%;"></div>
    </div>
    <div class="skeleton-card">
      <div class="skeleton-meta"></div>
      <div class="skeleton-title"></div>
      <div class="skeleton-line" style="width: 95%;"></div>
      <div class="skeleton-line" style="width: 60%;"></div>
    </div>
    <div class="skeleton-card">
      <div class="skeleton-meta"></div>
      <div class="skeleton-title"></div>
      <div class="skeleton-line" style="width: 85%;"></div>
    </div>
  `;
}

function renderEmpty(container) {
  if (!container) return;
  container.innerHTML = `
    <div class="feed-empty-state">
      <div class="empty-icon">📰</div>
      <h4>No articles found</h4>
      <p>${currentSearch ? `No stories matching "${escapeHtml(currentSearch)}" in this category.` : 'No stories found for the selected category filter.'}</p>
      ${currentSearch ? '<button class="btn btn-secondary" onclick="document.getElementById(\'searchClearBtn\').click()">Clear Search</button>' : ''}
    </div>
  `;
}

function renderError(container, message, retryFn) {
  if (!container) return;
  container.innerHTML = `
    <div class="feed-error-state">
      <div class="error-icon">⚠️</div>
      <h4>Unable to load feed</h4>
      <p>${escapeHtml(message)}</p>
      <button class="btn btn-primary btn-retry">Retry</button>
    </div>
  `;
  const retryBtn = container.querySelector('.btn-retry');
  if (retryBtn) retryBtn.addEventListener('click', retryFn);
}

export function updateArticleState(articleId, updates) {
  const art = loadedArticles.find(a => a.id === articleId);
  if (art) {
    Object.assign(art, updates);
    const cardEl = document.getElementById(`card-${articleId}`);
    if (cardEl) {
      if (updates.is_read !== undefined) {
        cardEl.classList.toggle('is-read', Boolean(updates.is_read));
        const newDot = cardEl.querySelector('.new-dot');
        if (newDot) newDot.style.display = updates.is_read ? 'none' : 'inline-block';
      }
      if (updates.is_bookmarked !== undefined) {
        const bkmkBtn = cardEl.querySelector('.btn-bookmark-card');
        if (bkmkBtn) {
          bkmkBtn.classList.toggle('active', Boolean(updates.is_bookmarked));
          bkmkBtn.innerHTML = updates.is_bookmarked ? '★' : '☆';
        }
      }
    }
  }
}
