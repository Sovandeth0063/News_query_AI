let currentFilter = 'AI_DS';
let currentSort = 'score';
let allArticles = [];
let papers = [];
let activeArticleId = null;

// Client-side guard: domains that should never appear in the feed
const JUNK_DOMAINS = [
  'example.com', 'example.org', 'example.net',
  'localhost', '127.0.0.1', '0.0.0.0',
  'test.com', 'foo.com', 'bar.com',
  'placeholder', 'dummy'
];

function isValidArticle(a) {
  if (!a || !a.title || !a.title.trim()) return false;
  if (!a.url || !a.url.trim()) return false;
  const url = a.url.toLowerCase();
  if (!url.startsWith('http://') && !url.startsWith('https://')) return false;
  return !JUNK_DOMAINS.some(d => url.includes(d));
}

document.addEventListener('DOMContentLoaded', () => {
  loadArticles();

  // Keyboard shortcut: ESC to close reader modal
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') {
      closeReader();
      const aiSec = document.getElementById('aiSection');
      if (aiSec && aiSec.style.display !== 'none') {
        aiSec.style.display = 'none';
      }
    }
  });
});

async function loadArticles() {
  const list = document.getElementById('newsList');
  list.innerHTML = `
    <div class="empty-state">
      <div class="spinner"></div>
      <p>Loading fresh news...</p>
    </div>
  `;
  try {
    const res = await fetch('/api/feed?limit=100');
    const data = await res.json();
    allArticles = data.articles || [];

    updateStatsBadge();
    renderCurrentView();
  } catch (err) {
    list.innerHTML = `<div class="empty-state" style="color: #ef4444;">Failed to load news: ${escapeHtml(err.message)}</div>`;
  }
}

async function loadPapers() {
  if (papers.length > 0) return;
  try {
    const res = await fetch('/api/papers?limit=60');
    const data = await res.json();
    papers = data.papers || [];
  } catch (err) {
    console.error('Failed to load papers:', err);
  }
}

function updateStatsBadge() {
  const badge = document.getElementById('articleCountBadge');
  badge.textContent = `${allArticles.length} articles`;
}

function setFilter(filter, btn) {
  currentFilter = filter;
  document.querySelectorAll('.pill-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');

  const digestView = document.getElementById('digestView');
  const newsList = document.getElementById('newsList');
  const feedInfoBar = document.querySelector('.feed-info-bar');

  if (filter === 'DIGEST') {
    newsList.style.display = 'none';
    feedInfoBar.style.display = 'none';
    digestView.style.display = 'block';
    loadDigest();
  } else {
    digestView.style.display = 'none';
    newsList.style.display = 'flex';
    feedInfoBar.style.display = 'flex';

    if (filter === 'PAPERS') {
      loadPapers().then(() => renderCurrentView());
    } else {
      renderCurrentView();
    }
  }
}

function onSortChange() {
  currentSort = document.getElementById('sortSelect').value;
  renderCurrentView();
}

function filterArticles() {
  const query = (document.getElementById('searchInput').value || '').trim();
  const clearBtn = document.getElementById('searchClearBtn');
  clearBtn.style.display = query.length > 0 ? 'inline-block' : 'none';
  renderCurrentView();
}

function clearSearch() {
  const input = document.getElementById('searchInput');
  input.value = '';
  document.getElementById('searchClearBtn').style.display = 'none';
  input.focus();
  renderCurrentView();
}

function getFilteredAndSortedArticles() {
  const query = (document.getElementById('searchInput').value || '').toLowerCase().trim();
  let items = [];

  if (currentFilter === 'AI_DS') {
    items = allArticles.filter(a =>
      a.category === 'AI_LLM' || a.category === 'DATA_SCIENCE_ML' || a.category === 'AI_RESEARCH'
    );
  } else if (currentFilter === 'PAPERS') {
    items = papers.length > 0 ? papers : allArticles.filter(a => a.category === 'AI_RESEARCH');
  } else if (currentFilter === 'BOOKMARKS') {
    items = allArticles.filter(a => Boolean(a.is_bookmarked));
  } else {
    items = allArticles;
  }

  // Drop invalid / placeholder articles before rendering
  items = items.filter(isValidArticle);

  // Keyword search filter
  if (query) {
    items = items.filter(a => {
      const titleMatch = a.title && a.title.toLowerCase().includes(query);
      const summaryMatch = a.summary && a.summary.toLowerCase().includes(query);
      const sourceMatch = a.source_name && a.source_name.toLowerCase().includes(query);
      const tagsMatch = a.tags && Array.isArray(a.tags) && a.tags.some(t => t.toLowerCase().includes(query));
      return titleMatch || summaryMatch || sourceMatch || tagsMatch;
    });
  }

  // Sort
  if (currentSort === 'date') {
    items.sort((a, b) => new Date(b.published_at_utc) - new Date(a.published_at_utc));
  } else {
    items.sort((a, b) => (b.score_cached || 0) - (a.score_cached || 0) || new Date(b.published_at_utc) - new Date(a.published_at_utc));
  }

  return items;
}

function renderCurrentView() {
  const list = document.getElementById('newsList');
  const countText = document.getElementById('feedCountText');
  const items = getFilteredAndSortedArticles();

  countText.textContent = `Showing ${items.length} ${items.length === 1 ? 'article' : 'articles'}`;

  if (items.length === 0) {
    list.innerHTML = `
      <div class="empty-state">
        <p>No articles found for the selected filter or search term.</p>
      </div>
    `;
    return;
  }

  list.innerHTML = items.map(a => renderCard(a)).join('');
}

function renderCard(a) {
  let badgeClass = 'badge-tech';
  let badgeLabel = 'Tech';

  if (a.category === 'AI_LLM') {
    badgeClass = 'badge-ai';
    badgeLabel = 'AI / LLM';
  } else if (a.category === 'DATA_SCIENCE_ML') {
    badgeClass = 'badge-ds';
    badgeLabel = 'Data Science';
  } else if (a.category === 'AI_RESEARCH') {
    badgeClass = 'badge-paper';
    badgeLabel = 'arXiv Paper';
  }

  const clusterTag = (a.cluster_size && a.cluster_size > 1)
    ? `<span class="cluster-badge" title="Covered by ${a.cluster_size} sources">⚡ ${a.cluster_size} sources</span>` : '';

  const timeAgo = formatTimeAgo(a.published_at_utc);
  const isBookmarked = Boolean(a.is_bookmarked);
  const isRead = Boolean(a.is_read);

  return `
    <article class="news-card ${isRead ? 'is-read' : ''}" id="card-${a.id}">
      <div class="card-top">
        <div class="card-meta-left">
          <span class="badge ${badgeClass}">${badgeLabel}</span>
          <span class="source-name">${escapeHtml(a.source_name || 'Source')}</span>
          ${clusterTag}
          <span class="time-ago">${timeAgo}</span>
        </div>
        <div class="card-actions-top">
          <button class="btn-action-icon ${isBookmarked ? 'bookmarked' : ''}"
                  onclick="toggleBookmark('${a.id}', event)"
                  title="${isBookmarked ? 'Remove bookmark' : 'Save article'}">
            ${isBookmarked ? '★' : '☆'}
          </button>
        </div>
      </div>

      <h3 class="card-title" onclick="openReader('${a.id}')">
        ${escapeHtml(a.title)}
      </h3>

      <p class="card-summary" onclick="openReader('${a.id}')">
        ${escapeHtml(a.summary || '')}
      </p>

      <div class="card-footer">
        <button class="btn-read" onclick="openReader('${a.id}')">
          Read story →
        </button>
        <a href="${a.url}" target="_blank" rel="noopener noreferrer" class="external-link" onclick="event.stopPropagation()">
          ${escapeHtml(a.source_name || 'Source')} ↗
        </a>
      </div>
    </article>
  `;
}

// In-App Article Reader Modal
async function openReader(articleId) {
  activeArticleId = articleId;
  const backdrop = document.getElementById('readerModalBackdrop') || document.getElementById('readerBackdrop');
  if (!backdrop) return;

  // Find article in local cache
  const localArt = allArticles.find(a => a.id === articleId) || papers.find(a => a.id === articleId) || {};

  const titleEl = document.getElementById('readerTitle');
  if (titleEl) titleEl.textContent = localArt.title || 'Loading...';
  const sourceEl = document.getElementById('readerSource');
  if (sourceEl) sourceEl.textContent = localArt.source_name || 'Source';
  const dateEl = document.getElementById('readerDate');
  if (dateEl) dateEl.textContent = formatTimeAgo(localArt.published_at_utc);
  const catEl = document.getElementById('readerCategory');
  if (catEl) catEl.textContent = localArt.category || 'Tech';
  const sumEl = document.getElementById('readerSummary') || document.getElementById('readerSummaryText');
  if (sumEl) sumEl.textContent = localArt.summary || '';
  const origBtn = document.getElementById('readerOpenOriginalBtn') || document.getElementById('readerExternalLink');
  if (origBtn) origBtn.href = localArt.url || '#';
  const bkmkBtn = document.getElementById('readerBookmarkBtn');
  if (bkmkBtn) {
    bkmkBtn.setAttribute('aria-pressed', localArt.is_bookmarked ? 'true' : 'false');
    const star = bkmkBtn.querySelector('.bookmark-star');
    if (star) star.textContent = localArt.is_bookmarked ? '★' : '☆';
  }

  // Clear previous body/tags/siblings
  const bodyElem = document.getElementById('readerFullBodyText') || document.getElementById('readerBody');
  if (bodyElem) bodyElem.innerHTML = '';
  const tagsContainer = document.getElementById('readerTags');
  if (tagsContainer) tagsContainer.innerHTML = '';
  const sibBox = document.getElementById('readerSiblingsBox') || document.getElementById('readerSiblings');
  if (sibBox) sibBox.style.display = 'none';

  backdrop.style.display = 'flex';
  document.body.style.overflow = 'hidden';

  // Mark as read locally and in backend
  markArticleAsRead(articleId);

  // Fetch full details
  try {
    const res = await fetch(`/api/articles/${articleId}`);
    if (!res.ok) throw new Error('Could not fetch article details');
    const data = await res.json();
    const art = data.article;
    const siblings = data.siblings || [];

    if (titleEl) titleEl.textContent = art.title;
    if (sourceEl) sourceEl.textContent = art.source_name || 'Source';
    if (dateEl) dateEl.textContent = formatTimeAgo(art.published_at_utc);
    if (sumEl) sumEl.textContent = art.summary || '';
    if (origBtn) origBtn.href = art.url;

    // Render tags
    if (tagsContainer && art.tags && art.tags.length > 0) {
      tagsContainer.innerHTML = art.tags.map(t => `<span class="reader-tag">#${escapeHtml(t)}</span>`).join('');
    }

    // Render Body
    if (bodyElem) {
      if (art.body && art.body.trim()) {
        const paragraphs = art.body.split(/\n{2,}|\n/).filter(p => p.trim().length > 0);
        bodyElem.innerHTML = paragraphs.map(p => `<p style="margin-bottom: 1rem;">${escapeHtml(p)}</p>`).join('');
      } else {
        bodyElem.innerHTML = `
          <p style="color: var(--text-muted); font-style: italic;">
            Full extracted text not available for this article preview. 
            <a href="${art.url}" target="_blank" rel="noopener noreferrer">Read the complete story ↗</a>
          </p>
        `;
      }
    }

    // Render Siblings
    if (siblings.length > 0 && sibBox) {
      const sibList = document.getElementById('readerSiblingsList');
      sibBox.style.display = '';
      if (sibList) {
        sibList.innerHTML = siblings.map(s => `
          <a href="${s.url}" target="_blank" rel="noopener noreferrer" class="sibling-chip">
            ${escapeHtml(s.source_name || 'Source')} ↗
          </a>
        `).join('');
      }
    }

  } catch (err) {
    if (bodyElem) {
      bodyElem.innerHTML = `<p style="color: #ef4444;">Notice: ${escapeHtml(err.message)}.</p>`;
    }
  }
}

function closeReader(event) {
  if (event && event.target !== event.currentTarget) return;
  const backdrop = document.getElementById('readerModalBackdrop') || document.getElementById('readerBackdrop');
  if (backdrop) backdrop.style.display = 'none';
  document.body.style.overflow = '';
  activeArticleId = null;
}

// Read and Bookmark state actions
async function markArticleAsRead(articleId) {
  const art = allArticles.find(a => a.id === articleId) || papers.find(a => a.id === articleId);
  if (art) {
    art.is_read = 1;
  }
  const card = document.getElementById(`card-${articleId}`);
  if (card) {
    card.classList.add('is-read');
  }
  try {
    await fetch(`/api/articles/${articleId}/read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_read: true })
    });
  } catch (e) {
    console.error('Error saving read state:', e);
  }
}

async function toggleBookmark(articleId, event) {
  if (event) event.stopPropagation();
  const art = allArticles.find(a => a.id === articleId) || papers.find(a => a.id === articleId);
  if (!art) return;

  const newState = !art.is_bookmarked;
  art.is_bookmarked = newState ? 1 : 0;

  // Update card icon
  const card = document.getElementById(`card-${articleId}`);
  if (card) {
    const btn = card.querySelector('.btn-action-icon');
    if (btn) {
      btn.textContent = newState ? '★' : '☆';
      btn.classList.toggle('bookmarked', newState);
      btn.title = newState ? 'Remove bookmark' : 'Bookmark this article';
    }
  }

  // Update modal icon if active
  if (activeArticleId === articleId) {
    document.getElementById('readerBookmarkBtn').textContent = newState ? '★' : '☆';
  }

  if (currentFilter === 'BOOKMARKS') {
    renderCurrentView();
  }

  try {
    await fetch(`/api/articles/${articleId}/bookmark`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_bookmarked: newState })
    });
  } catch (e) {
    console.error('Error updating bookmark:', e);
  }
}

function toggleReaderBookmark() {
  if (activeArticleId) {
    toggleBookmark(activeArticleId);
  }
}

// Collapsible Ask AI
function toggleAiDrawer() {
  const section = document.getElementById('aiSection');
  const isHidden = section.style.display === 'none' || section.style.display === '';
  section.style.display = isHidden ? 'block' : 'none';
  const btn = document.getElementById('btnToggleAi');
  if (btn) btn.style.background = isHidden ? 'var(--blue-50)' : '';
  if (isHidden) {
    setTimeout(() => document.getElementById('aiQueryInput').focus(), 50);
  }
}

async function askAI() {
  const input = document.getElementById('aiQueryInput');
  const question = input.value.trim();
  if (!question) return;

  const box = document.getElementById('aiResponseBox');
  const answerElem = document.getElementById('aiAnswer');
  const sourcesElem = document.getElementById('aiSources');
  const badge = document.getElementById('aiModelBadge');

  box.style.display = 'block';
  answerElem.textContent = 'Searching articles and synthesizing answer...';
  sourcesElem.innerHTML = '';

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question })
    });
    const data = await res.json();
    badge.textContent = data.model_used || 'Gemini 3+';

    let formattedAnswer = escapeHtml(data.answer);
    if (data.sources && data.sources.length > 0) {
      formattedAnswer = formattedAnswer.replace(/\[(\d+)\]/g, (match, num) => {
        const src = data.sources.find(s => s.index == num);
        if (src && src.url) {
          return `<a href="${src.url}" target="_blank" style="color: var(--accent-ds); font-weight: 700;">[${num}]</a>`;
        }
        return match;
      });

      sourcesElem.innerHTML = '<b>Cited Sources:</b> ' + data.sources.map(s => `
        <a href="${s.url}" target="_blank">[${s.index}] ${escapeHtml(s.title)} (${escapeHtml(s.source)}) ↗</a>
      `).join(' ');
    }

    answerElem.innerHTML = formattedAnswer;
  } catch (err) {
    answerElem.textContent = `Error: ${err.message}`;
  }
}

// Daily Digest
async function loadDigest() {
  const body = document.getElementById('digestBody');
  body.innerHTML = `
    <div class="empty-state">
      <div class="spinner"></div>
      <p>Loading executive briefing...</p>
    </div>
  `;
  try {
    const res = await fetch('/api/digest');
    const data = await res.json();
    document.getElementById('digestTitle').textContent = `Daily AI Briefing (${data.digest_date})`;
    if (window.marked) {
      body.innerHTML = marked.parse(data.content_md);
    } else {
      body.innerText = data.content_md;
    }
  } catch (err) {
    body.innerHTML = `<div class="empty-state" style="color: #ef4444;">Error loading digest: ${escapeHtml(err.message)}</div>`;
  }
}

async function regenerateDigest() {
  const body = document.getElementById('digestBody');
  body.innerHTML = `
    <div class="empty-state">
      <div class="spinner"></div>
      <p>Generating fresh executive briefing with Gemini 3+...</p>
    </div>
  `;
  try {
    const res = await fetch('/api/digest/generate', { method: 'POST' });
    const data = await res.json();
    document.getElementById('digestTitle').textContent = `Daily AI Briefing (${data.digest_date})`;
    if (window.marked) {
      body.innerHTML = marked.parse(data.content_md);
    } else {
      body.innerText = data.content_md;
    }
  } catch (err) {
    body.innerHTML = `<div class="empty-state" style="color: #ef4444;">Error generating digest: ${escapeHtml(err.message)}</div>`;
  }
}

// Background Sync
async function triggerSync() {
  const statusElem = document.getElementById('syncStatus');
  const btn = document.getElementById('btnSync');
  const icon = document.getElementById('syncIcon');
  
  btn.disabled = true;
  if (icon) icon.classList.add('spinner');
  statusElem.textContent = 'Starting sync...';

  try {
    const res = await fetch('/api/sync', { method: 'POST' });
    const data = await res.json();

    const interval = setInterval(async () => {
      try {
        const sRes = await fetch(`/api/sync/${data.run_id}`);
        const sData = await sRes.json();
        statusElem.textContent = `${sData.percent}% ${sData.message}`;

        if (sData.status === 'completed' || sData.status === 'failed') {
          clearInterval(interval);
          btn.disabled = false;
          if (icon) icon.classList.remove('spinner');
          statusElem.textContent = sData.status === 'completed' ? 'Synced!' : 'Failed';
          loadArticles();
        }
      } catch (e) {
        clearInterval(interval);
        btn.disabled = false;
        if (icon) icon.classList.remove('spinner');
      }
    }, 1200);

  } catch (err) {
    statusElem.textContent = 'Sync failed';
    btn.disabled = false;
    if (icon) icon.classList.remove('spinner');
  }
}

// Helper Utilities
function formatTimeAgo(isoDate) {
  if (!isoDate) return '';
  const dt = new Date(isoDate);
  const now = new Date();
  const diffSec = Math.floor((now - dt) / 1000);
  if (diffSec < 60) return 'Just now';
  if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
  if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
  return `${Math.floor(diffSec / 86400)}d ago`;
}

function escapeHtml(text) {
  if (!text) return '';
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
