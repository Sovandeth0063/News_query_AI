/**
 * Application Entry Point: Coordinates Theme, Tabs, Feed, Papers, Digest,
 * Ask AI Chat, Sources Drawer, Sync, Sidebar Widgets, and Shortcuts Modal.
 */

import { initTheme, toggleTheme } from './theme.js';
import { initTabs } from './tabs.js';
import { initFeed, loadFeed, updateArticleState } from './feed.js';
import { initPapers } from './papers.js';
import { initDigest } from './digest.js';
import { initChat, focusChatInput } from './chat.js';
import { initSync } from './sync.js';
import { initSourcesDrawer, refreshSourcesSummary } from './sources.js';
import { initReaderModal } from './modal.js';
import { initSidebar, loadSidebarData } from './sidebar.js';
import { initRadar, loadRadarFeed } from './radar.js';

import { api } from './api.js';

document.addEventListener('DOMContentLoaded', () => {
  // 1. Initialize Theme (syncs toggle button, listens to OS)
  initTheme();

  // 2. Initialize Modal & Drawer systems
  initReaderModal((articleId, updates) => {
    updateArticleState(articleId, updates);
  });
  initSourcesDrawer();
  initShortcutsModal();

  // 3. Initialize Feed & Dynamic Sidebar
  initFeed();
  initSidebar();

  // Initialize Radar badge count on startup
  api.getRadar({ days: 7 }).then(res => {
    const badge = document.getElementById('radarCountBadge');
    if (badge && res.items && res.items.length > 0) {
      badge.textContent = `${res.items.length} New`;
    }
  }).catch(() => {});

  // 4. Initialize Tabs with Lazy-loading for non-default tabs
  initTabs((tabId, panelId) => {
    if (tabId === 'tabRadar') {
      initRadar();
    } else if (tabId === 'tabPapers') {
      initPapers();
    } else if (tabId === 'tabDigest') {
      initDigest();
    } else if (tabId === 'tabChat') {
      initChat();
      focusChatInput();
    }
  });

  // 5. Initialize Sync Manager
  initSync(() => {
    // On sync completion, reload active feed, sidebar, radar, and source health
    loadFeed(true);
    loadRadarFeed();
    loadSidebarData();
    refreshSourcesSummary();
  });
});

function initShortcutsModal() {
  const modal = document.getElementById('shortcutsModalBackdrop');
  const openBtn = document.getElementById('shortcutsModalBtn');
  const closeBtn = document.getElementById('shortcutsCloseBtn');
  if (!modal) return;

  function openModal() {
    modal.style.display = 'flex';
    modal.setAttribute('aria-hidden', 'false');
  }

  function closeModal() {
    modal.style.display = 'none';
    modal.setAttribute('aria-hidden', 'true');
  }

  if (openBtn) {
    openBtn.addEventListener('click', openModal);
  }
  if (closeBtn) {
    closeBtn.addEventListener('click', closeModal);
  }

  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeModal();
  });

  document.addEventListener('keydown', (e) => {
    // Escape closes modal
    if (e.key === 'Escape' && modal.style.display === 'flex') {
      closeModal();
      return;
    }

    // Ignore single key shortcuts when inside input/textarea
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(document.activeElement?.tagName)) {
      return;
    }

    // "?" opens shortcuts dialog
    if (e.key === '?') {
      e.preventDefault();
      if (modal.style.display === 'flex') {
        closeModal();
      } else {
        openModal();
      }
    }

    // "T" toggles theme
    if (e.key === 't' || e.key === 'T') {
      toggleTheme();
    }
  });
}
