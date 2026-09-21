/**
 * Sidebar Module: Dynamic Intelligence Widgets
 * - Top 3 stories today with takeaways
 * - Topic counts pill cloud
 * - Latest daily digest preview with instant tab navigation
 */

import { api } from './api.js';
import { escapeHtml, formatTimeAgo, isValidHttpUrl } from './utils.js';
import { switchTab } from './tabs.js';

export function initSidebar() {
  loadSidebarData();
}

export async function loadSidebarData() {
  const topTodayEl = document.getElementById('sidebarTopToday');
  const topicCountsEl = document.getElementById('sidebarTopicCounts');
  const digestPreviewEl = document.getElementById('sidebarDigestPreview');

  try {
    const data = await api.getSidebarData();
    if (!data) return;

    // 1. Render Top 3 Stories Today
    if (topTodayEl) {
      const topItems = data.top_today || [];
      if (topItems.length === 0) {
        topTodayEl.innerHTML = '<p class="sidebar-empty">No stories available today yet.</p>';
      } else {
        topTodayEl.innerHTML = topItems.map((item, idx) => {
          const safeUrl = isValidHttpUrl(item.url) ? item.url : '#';
          const takeaway = item.takeaway || item.summary || '';
          return `
            <div class="sidebar-story-item">
              <div class="sidebar-story-meta">
                <span class="sidebar-story-num">#${idx + 1}</span>
                <span class="source-name">${escapeHtml(item.source_name || 'Source')}</span>
                <span class="time-ago">${formatTimeAgo(item.published_at_utc)}</span>
              </div>
              <h4 class="sidebar-story-title">
                <a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer" class="title-link">
                  ${escapeHtml(item.title)}
                </a>
              </h4>
              <p class="sidebar-story-takeaway">
                ${escapeHtml(takeaway)}
              </p>
            </div>
          `;
        }).join('');
      }
    }

    // 2. Render Topic Counts Cloud
    if (topicCountsEl) {
      const topics = data.topic_counts || [];
      if (topics.length === 0) {
        topicCountsEl.innerHTML = '<p class="sidebar-empty">No active topics found.</p>';
      } else {
        topicCountsEl.innerHTML = topics.map(t => `
          <button class="topic-count-pill" data-topic="${escapeHtml(t.tag)}" title="Filter feed by ${escapeHtml(t.tag)}">
            <span class="topic-name">#${escapeHtml(t.tag)}</span>
            <span class="topic-num">${t.count}</span>
          </button>
        `).join('');

        // Wire topic clicks to search the feed
        topicCountsEl.querySelectorAll('.topic-count-pill').forEach(btn => {
          btn.addEventListener('click', () => {
            const topic = btn.dataset.topic;
            const searchInput = document.getElementById('globalSearchInput');
            if (searchInput && topic) {
              searchInput.value = topic;
              searchInput.dispatchEvent(new Event('input', { bubbles: true }));
              switchTab('tabFeed');
            }
          });
        });
      }
    }

    // 3. Render Latest Digest Preview
    if (digestPreviewEl) {
      const digest = data.digest_preview;
      if (!digest) {
        digestPreviewEl.innerHTML = `
          <p class="sidebar-empty">No briefing generated yet.</p>
          <button class="sidebar-digest-link" id="sidebarGoDigestBtn">Generate or view briefings →</button>
        `;
      } else {
        digestPreviewEl.innerHTML = `
          <div class="sidebar-digest-date">Briefing for ${escapeHtml(digest.digest_date || 'Today')}</div>
          <p class="sidebar-digest-snippet">${escapeHtml(digest.snippet || '')}</p>
          <button class="sidebar-digest-link" id="sidebarGoDigestBtn">
            Read full briefing →
          </button>
        `;
      }

      const goBtn = document.getElementById('sidebarGoDigestBtn');
      if (goBtn) {
        goBtn.addEventListener('click', () => {
          switchTab('tabDigest');
        });
      }
    }

  } catch (err) {
    console.warn('Failed to load sidebar data:', err);
    if (topTodayEl) {
      topTodayEl.innerHTML = '<p class="sidebar-empty">Unable to load top stories.</p>';
    }
  }
}
