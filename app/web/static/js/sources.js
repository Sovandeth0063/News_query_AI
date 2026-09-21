/**
 * Sources Health Drawer Controller
 */

import { api } from './api.js';
import { escapeHtml, formatTimeAgo, trapFocus, releaseFocus } from './utils.js';

let drawerEl = null;
let abortCtrl = null;

export function initSourcesDrawer() {
  drawerEl = document.getElementById('sourcesDrawer');
  const openBtn = document.getElementById('sourcesDrawerBtn');
  const closeBtn = document.getElementById('sourcesCloseBtn');

  if (openBtn) {
    openBtn.addEventListener('click', () => openSourcesDrawer());
  }

  if (closeBtn) {
    closeBtn.addEventListener('click', () => closeSourcesDrawer());
  }

  if (drawerEl) {
    drawerEl.addEventListener('click', (e) => {
      if (e.target === drawerEl) {
        closeSourcesDrawer();
      }
    });
  }

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && drawerEl && drawerEl.classList.contains('open')) {
      closeSourcesDrawer();
    }
  });

  // Load initial health state to update header badge
  refreshSourcesSummary();
}

export async function refreshSourcesSummary() {
  try {
    const data = await api.getSources();
    const sources = data.sources || [];
    const countBadge = document.getElementById('sourcesCountBadge');
    const healthDot = document.getElementById('sourcesHealthDot');

    if (countBadge) {
      countBadge.textContent = `${sources.length} sources`;
    }

    const hasErrors = sources.some(s => s.consecutive_failures > 0);
    if (healthDot) {
      healthDot.classList.toggle('has-error', hasErrors);
      healthDot.setAttribute('title', hasErrors ? 'Some sources encountered errors' : 'All sources healthy');
    }
  } catch (e) {
    // Non-fatal
  }
}

export async function openSourcesDrawer() {
  if (!drawerEl) return;
  drawerEl.classList.add('open');
  document.body.style.overflow = 'hidden';
  trapFocus(drawerEl.querySelector('.drawer-content') || drawerEl);

  const listEl = document.getElementById('sourcesList');
  if (listEl) {
    listEl.innerHTML = `
      <div class="drawer-loading">
        <div class="skeleton-shimmer" style="height: 50px; margin-bottom: 8px; border-radius: 8px;"></div>
        <div class="skeleton-shimmer" style="height: 50px; margin-bottom: 8px; border-radius: 8px;"></div>
        <div class="skeleton-shimmer" style="height: 50px; border-radius: 8px;"></div>
      </div>
    `;
  }

  if (abortCtrl) abortCtrl.abort();
  abortCtrl = new AbortController();

  try {
    const data = await api.getSources({ signal: abortCtrl.signal });
    const sources = data.sources || [];

    if (sources.length === 0) {
      listEl.innerHTML = `<div class="empty-state"><p>No news sources configured yet.</p></div>`;
      return;
    }

    listEl.innerHTML = sources.map(s => {
      const hasFailures = s.consecutive_failures > 0;
      const lastSync = s.last_success_at ? formatTimeAgo(s.last_success_at) : 'Never';

      return `
        <div class="source-item ${hasFailures ? 'source-warning' : ''}">
          <div class="source-info">
            <div class="source-header-row">
              <span class="source-name">${escapeHtml(s.name)}</span>
              <span class="source-kind-badge">${escapeHtml(s.kind || 'rss').toUpperCase()}</span>
            </div>
            <div class="source-meta">
              <span>Authority: ${(s.authority ?? 1.0).toFixed(2)}</span>
              <span>·</span>
              <span>Last sync: ${lastSync}</span>
            </div>
          </div>
          <div class="source-status-badge ${hasFailures ? 'status-failing' : 'status-healthy'}" 
               title="${hasFailures ? `Failed ${s.consecutive_failures} consecutive times` : 'Healthy'}">
            ${hasFailures ? `⚠ ${s.consecutive_failures} err` : '✓ OK'}
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    if (err.name === 'AbortError') return;
    if (listEl) {
      listEl.innerHTML = `<div class="empty-state error"><p>Error loading sources: ${escapeHtml(err.message)}</p></div>`;
    }
  }
}

export function closeSourcesDrawer() {
  if (!drawerEl) return;
  drawerEl.classList.remove('open');
  document.body.style.overflow = '';
  releaseFocus();
  if (abortCtrl) {
    abortCtrl.abort();
    abortCtrl = null;
  }
}
