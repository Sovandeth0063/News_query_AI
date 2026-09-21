/**
 * Digest Controller: Executive Briefing with Safe Markdown Rendering,
 * Date Picker, Confirmation Modal, Cooldown Timer, and 429 Quota Guards.
 */

import { api, ApiError } from './api.js';
import { renderSafeMarkdown, escapeHtml, trapFocus, releaseFocus } from './utils.js';
import { showToast } from './toast.js';

let currentDate = new Date().toISOString().split('T')[0];
let cooldownTimer = null;
let cooldownRemaining = 0;
let abortCtrl = null;
let initialized = false;

export function initDigest() {
  if (initialized) return;
  initialized = true;

  bindEvents();
  loadDigest();
}

function bindEvents() {
  const dateInput = document.getElementById('digestDatePicker');
  if (dateInput) {
    dateInput.value = currentDate;
    dateInput.addEventListener('change', (e) => {
      currentDate = e.target.value;
      loadDigest();
    });
  }

  const regenBtn = document.getElementById('digestRegenerateBtn');
  if (regenBtn) {
    regenBtn.addEventListener('click', () => {
      if (cooldownRemaining > 0) {
        showToast(`Please wait ${cooldownRemaining}s before regenerating again.`, 'warning');
        return;
      }
      openConfirmModal();
    });
  }

  // Confirmation modal buttons
  const confirmModal = document.getElementById('regenConfirmModal');
  const confirmBtn = document.getElementById('regenConfirmProceed');
  const cancelBtn = document.getElementById('regenConfirmCancel');

  if (confirmBtn) {
    confirmBtn.addEventListener('click', () => {
      closeConfirmModal();
      regenerateDigest();
    });
  }

  if (cancelBtn) {
    cancelBtn.addEventListener('click', closeConfirmModal);
  }

  if (confirmModal) {
    confirmModal.addEventListener('click', (e) => {
      if (e.target === confirmModal) closeConfirmModal();
    });
  }
}

function openConfirmModal() {
  const modal = document.getElementById('regenConfirmModal');
  if (!modal) return;
  modal.style.display = 'flex';
  trapFocus(modal.querySelector('.confirm-dialog') || modal);
}

function closeConfirmModal() {
  const modal = document.getElementById('regenConfirmModal');
  if (!modal) return;
  modal.style.display = 'none';
  releaseFocus();
}

export async function loadDigest() {
  if (abortCtrl) abortCtrl.abort();
  abortCtrl = new AbortController();

  const bodyEl = document.getElementById('digestContentBody');
  const titleEl = document.getElementById('digestTitleLabel');

  renderSkeleton(bodyEl);
  if (titleEl) titleEl.textContent = `Daily Intelligence Briefing (${currentDate})`;

  try {
    const data = await api.getDigest(currentDate, { signal: abortCtrl.signal });

    if (!data || !data.content_md || !data.content_md.trim()) {
      renderEmpty(bodyEl);
      return;
    }

    if (data.digest_date && titleEl) {
      titleEl.textContent = `Daily Intelligence Briefing (${data.digest_date})`;
    }

    bodyEl.innerHTML = renderSafeMarkdown(data.content_md);

  } catch (err) {
    if (err.name === 'AbortError') return;
    if (err instanceof ApiError && err.status === 429) {
      bodyEl.innerHTML = `
        <div class="feed-error-state">
          <div class="error-icon">⏳</div>
          <h4>Rate Limit Exceeded</h4>
          <p>The AI service is currently busy. Please wait a moment before refreshing.</p>
        </div>
      `;
      return;
    }
    renderError(bodyEl, err.message, () => loadDigest());
  }
}

async function regenerateDigest() {
  const bodyEl = document.getElementById('digestContentBody');
  const regenBtn = document.getElementById('digestRegenerateBtn');

  renderGeneratingSkeleton(bodyEl);
  startCooldown(60);

  try {
    const data = await api.generateDigest(currentDate);
    showToast('Fresh briefing synthesized successfully!', 'success');
    if (data && data.content_md) {
      bodyEl.innerHTML = renderSafeMarkdown(data.content_md);
    } else {
      loadDigest();
    }
  } catch (err) {
    if (err instanceof ApiError && err.status === 429) {
      showToast('AI quota rate limit reached. Please wait a few minutes.', 'error');
    } else {
      showToast(`Regeneration failed: ${err.message}`, 'error');
    }
    loadDigest();
  }
}

function startCooldown(seconds) {
  cooldownRemaining = seconds;
  const regenBtn = document.getElementById('digestRegenerateBtn');

  if (cooldownTimer) clearInterval(cooldownTimer);

  const updateBtnText = () => {
    if (!regenBtn) return;
    if (cooldownRemaining > 0) {
      regenBtn.disabled = true;
      regenBtn.innerHTML = `⏳ Regenerate (${cooldownRemaining}s)`;
    } else {
      regenBtn.disabled = false;
      regenBtn.innerHTML = `🔄 Regenerate Briefing`;
    }
  };

  updateBtnText();

  cooldownTimer = setInterval(() => {
    cooldownRemaining -= 1;
    if (cooldownRemaining <= 0) {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
    }
    updateBtnText();
  }, 1000);
}

function renderSkeleton(container) {
  if (!container) return;
  container.innerHTML = `
    <div class="skeleton-shimmer" style="height: 32px; width: 60%; margin-bottom: 20px; border-radius: 6px;"></div>
    <div class="skeleton-shimmer" style="height: 16px; width: 95%; margin-bottom: 12px; border-radius: 4px;"></div>
    <div class="skeleton-shimmer" style="height: 16px; width: 90%; margin-bottom: 12px; border-radius: 4px;"></div>
    <div class="skeleton-shimmer" style="height: 16px; width: 80%; margin-bottom: 24px; border-radius: 4px;"></div>
    <div class="skeleton-shimmer" style="height: 24px; width: 45%; margin-bottom: 16px; border-radius: 6px;"></div>
    <div class="skeleton-shimmer" style="height: 16px; width: 92%; margin-bottom: 10px; border-radius: 4px;"></div>
    <div class="skeleton-shimmer" style="height: 16px; width: 88%; margin-bottom: 10px; border-radius: 4px;"></div>
  `;
}

function renderGeneratingSkeleton(container) {
  if (!container) return;
  container.innerHTML = `
    <div class="digest-generating-box">
      <div class="spinner-large"></div>
      <h4>Synthesizing Executive Briefing…</h4>
      <p>Gemini is clustering today's high-authority stories and extracting key research insights.</p>
    </div>
  `;
}

function renderEmpty(container) {
  if (!container) return;
  container.innerHTML = `
    <div class="feed-empty-state">
      <div class="empty-icon">📑</div>
      <h4>No Briefing for ${escapeHtml(currentDate)}</h4>
      <p>An executive briefing has not yet been generated for this date.</p>
      <button class="btn btn-primary btn-generate-now" style="margin-top: 12px;">Generate Now</button>
    </div>
  `;
  const btn = container.querySelector('.btn-generate-now');
  if (btn) btn.addEventListener('click', () => openConfirmModal());
}

function renderError(container, message, retryFn) {
  if (!container) return;
  container.innerHTML = `
    <div class="feed-error-state">
      <div class="error-icon">⚠️</div>
      <h4>Failed to load briefing</h4>
      <p>${escapeHtml(message)}</p>
      <button class="btn btn-primary btn-retry-digest">Retry</button>
    </div>
  `;
  const btn = container.querySelector('.btn-retry-digest');
  if (btn) btn.addEventListener('click', retryFn);
}
