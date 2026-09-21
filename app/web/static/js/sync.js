/**
 * Sync Manager: Triggers background news ingestion, polls progress,
 * manages last-synced timestamp, and fires notifications.
 */

import { api, ApiError } from './api.js';
import { formatTimeAgo } from './utils.js';
import { showToast } from './toast.js';

const LAST_SYNCED_KEY = 'newsquery_last_synced_at';
let isSyncing = false;
let pollTimer = null;
let onSyncCompleteCallback = null;

export function initSync(onComplete) {
  onSyncCompleteCallback = onComplete;
  const syncBtn = document.getElementById('syncBtn');
  if (syncBtn) {
    syncBtn.addEventListener('click', handleSyncClick);
  }

  updateLastSyncedLabel();
  // Update the label periodically
  setInterval(updateLastSyncedLabel, 60000);
}

function updateLastSyncedLabel() {
  const labelEl = document.getElementById('lastSyncedLabel');
  if (!labelEl) return;
  const stored = localStorage.getItem(LAST_SYNCED_KEY);
  if (!stored) {
    labelEl.textContent = 'Not synced yet';
    return;
  }
  const ago = formatTimeAgo(stored);
  labelEl.textContent = ago ? `Synced ${ago}` : 'Just now';
}

export function recordSyncSuccess() {
  localStorage.setItem(LAST_SYNCED_KEY, new Date().toISOString());
  updateLastSyncedLabel();
}

async function handleSyncClick() {
  if (isSyncing) return;
  const syncBtn = document.getElementById('syncBtn');
  const syncIcon = document.getElementById('syncIcon');
  const syncText = document.getElementById('syncBtnText');

  isSyncing = true;
  syncBtn.disabled = true;
  syncIcon.classList.add('spinning');
  syncText.textContent = 'Syncing…';
  showToast('Starting background news sync…', 'info');

  try {
    const res = await api.triggerSync();
    const runId = res.run_id;
    pollSyncStatus(runId);
  } catch (err) {
    if (err instanceof ApiError && err.status === 409) {
      showToast('A sync is already in progress.', 'warning');
      // Still poll for completion
      pollSyncStatus('current');
    } else {
      showToast(`Sync failed to start: ${err.message}`, 'error');
      resetSyncButton();
    }
  }
}

function pollSyncStatus(runId) {
  if (pollTimer) clearInterval(pollTimer);

  const syncText = document.getElementById('syncBtnText');

  pollTimer = setInterval(async () => {
    try {
      const status = await api.getSyncStatus(runId);
      if (status.percent !== undefined) {
        syncText.textContent = `${status.percent}%`;
      }

      if (status.status === 'completed') {
        clearInterval(pollTimer);
        pollTimer = null;
        recordSyncSuccess();
        showToast('Sync complete! Refreshed feed with latest stories.', 'success');
        resetSyncButton();
        if (typeof onSyncCompleteCallback === 'function') {
          onSyncCompleteCallback();
        }
      } else if (status.status === 'failed') {
        clearInterval(pollTimer);
        pollTimer = null;
        showToast(`Sync failed: ${status.message || 'Unknown error'}`, 'error');
        resetSyncButton();
      }
    } catch (e) {
      // If run ID polling errors out, clean up
      clearInterval(pollTimer);
      pollTimer = null;
      resetSyncButton();
    }
  }, 1400);
}

function resetSyncButton() {
  isSyncing = false;
  const syncBtn = document.getElementById('syncBtn');
  const syncIcon = document.getElementById('syncIcon');
  const syncText = document.getElementById('syncBtnText');

  if (syncBtn) syncBtn.disabled = false;
  if (syncIcon) syncIcon.classList.remove('spinning');
  if (syncText) syncText.textContent = 'Sync Now';
}
