/**
 * Model Radar: "New Models & Updates" Tab Manager
 * Discovers newly launched models, tracked entities, coverage, and timelines.
 */

import { api } from './api.js';
import { escapeHtml, formatTimeAgo, isValidHttpUrl } from './utils.js';
import { showToast } from './toast.js';

const formatRelativeTime = formatTimeAgo;

let currentDays = 7;
let currentEventType = '';
let currentEmergingOnly = false;
let isInitialized = false;
let abortController = null;

export function initRadar() {
  if (isInitialized) return;
  isInitialized = true;

  const container = document.getElementById('radarPanel');
  if (!container) return;

  setupRadarFilters();
  setupTimelineModal();
  loadRadarFeed();
}

function setupRadarFilters() {
  const eventFilterPills = document.querySelectorAll('.radar-event-pill');
  eventFilterPills.forEach(pill => {
    pill.addEventListener('click', () => {
      eventFilterPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      currentEventType = pill.getAttribute('data-event') || '';
      loadRadarFeed();
    });
  });

  const emergingToggle = document.getElementById('radarEmergingToggle');
  if (emergingToggle) {
    emergingToggle.addEventListener('click', () => {
      currentEmergingOnly = !currentEmergingOnly;
      emergingToggle.classList.toggle('active', currentEmergingOnly);
      loadRadarFeed();
    });
  }

  const daysSelect = document.getElementById('radarDaysSelect');
  if (daysSelect) {
    daysSelect.addEventListener('change', (e) => {
      currentDays = parseInt(e.target.value, 10) || 7;
      loadRadarFeed();
    });
  }

  const reprocessBtn = document.getElementById('radarReprocessBtn');
  if (reprocessBtn) {
    reprocessBtn.addEventListener('click', async () => {
      reprocessBtn.disabled = true;
      reprocessBtn.innerHTML = `<span>⏳ Reprocessing...</span>`;
      showToast('Starting radar extraction for recent articles...', 'info');
      try {
        const res = await api.reprocessRadar(currentDays);
        showToast('Radar extraction completed!', 'success');
        loadRadarFeed();
      } catch (err) {
        showToast(`Extraction failed: ${err.message}`, 'error');
      } finally {
        reprocessBtn.disabled = false;
        reprocessBtn.innerHTML = `<span>⚡ Reprocess Radar</span>`;
      }
    });
  }
}

export async function loadRadarFeed() {
  const stream = document.getElementById('radarStream');
  if (!stream) return;

  if (abortController) {
    abortController.abort();
  }
  abortController = new AbortController();

  stream.innerHTML = `
    <div class="radar-loading" style="padding: 40px; text-align: center; color: var(--text-muted);">
      <div class="spinner" style="margin: 0 auto 12px;"></div>
      <p>Scanning for model launches, updates, and emerging intelligence...</p>
    </div>
  `;

  try {
    let items = [];
    if (currentEmergingOnly) {
      // Fetch emerging entities and their latest items
      const entRes = await api.getEntities({ emerging: true, limit: 30, signal: abortController.signal });
      const emergingEntities = entRes.entities || [];

      // Also get radar feed
      const res = await api.getRadar({
        days: currentDays,
        event_type: currentEventType || null,
        limit: 50,
        signal: abortController.signal
      });
      const allRadarItems = res.items || [];

      // Filter items linked to emerging entities
      const emergingIds = new Set(emergingEntities.map(e => e.id));
      items = allRadarItems.filter(item => 
        (item.entities || []).some(e => emergingIds.has(e.id) || e.is_emerging === 1)
      );

      // If no articles match but entities exist, render entity cards
      if (items.length === 0 && emergingEntities.length > 0) {
        renderEmergingEntitiesCards(emergingEntities, stream);
        return;
      }
    } else {
      const res = await api.getRadar({
        days: currentDays,
        event_type: currentEventType || null,
        limit: 50,
        signal: abortController.signal
      });
      items = res.items || [];
    }

    if (!items || items.length === 0) {
      stream.innerHTML = `
        <div class="radar-empty" style="padding: 50px 20px; text-align: center; color: var(--text-muted); border: 1px dashed var(--border-color); border-radius: var(--radius-lg); margin-top: 16px;">
          <div style="font-size: 32px; margin-bottom: 8px;">📡</div>
          <h4 style="color: var(--text-primary); margin-bottom: 6px;">No Model Radar Items Found</h4>
          <p style="max-width: 450px; margin: 0 auto 16px;">No articles matching "${currentEventType || 'model_release / update'}" were found in the last ${currentDays} days. Run ingestion or click "Reprocess Radar" to extract from ingested news.</p>
          <button class="btn btn-secondary" onclick="document.getElementById('radarReprocessBtn')?.click()">⚡ Run Radar Extraction</button>
        </div>
      `;
      return;
    }

    renderRadarCards(items, stream);

  } catch (err) {
    if (err.name === 'AbortError') return;
    stream.innerHTML = `
      <div class="radar-error" style="padding: 30px; text-align: center; color: var(--color-danger); border: 1px solid var(--color-danger); border-radius: var(--radius-md);">
        <p>Failed to load Model Radar feed: ${escapeHtml(err.message)}</p>
        <button class="btn btn-secondary" style="margin-top: 12px;" onclick="loadRadarFeed()">Retry</button>
      </div>
    `;
  }
}

function renderRadarCards(items, stream) {
  const cardsHtml = items.map(item => {
    const isRelease = item.event_type === 'model_release';
    const isUpdate = item.event_type === 'model_update';
    const eventBadgeClass = isRelease ? 'badge-release' : (isUpdate ? 'badge-update' : 'badge-general');
    const eventLabel = isRelease ? '🚀 Launch' : (isUpdate ? '🔄 Update' : (item.event_type || 'Event'));

    const entities = item.entities || [];
    const hasEmerging = entities.some(e => e.is_emerging === 1);

    const entityPills = entities.map(e => `
      <span class="radar-entity-tag ${e.is_emerging ? 'emerging' : ''}" data-entity-id="${e.id}" title="Click to view timeline">
        ${e.is_emerging ? '🔥 ' : ''}${escapeHtml(e.name)}
        <span class="entity-type-badge">${escapeHtml(e.type)}</span>
      </span>
    `).join('');

    const coverageBadge = item.coverage_count > 1 
      ? `<span class="radar-coverage-badge" title="Reported by ${item.coverage_count} distinct sources">📰 ${item.coverage_count} sources</span>`
      : '';

    const safeUrl = isValidHttpUrl(item.url) ? item.url : '#';
    const primaryEntity = entities.find(e => e.role === 'subject') || entities[0];
    const primaryEntityId = primaryEntity ? primaryEntity.id : '';

    return `
      <article class="radar-card" data-article-id="${escapeHtml(item.article_id)}" data-entity-id="${primaryEntityId}">
        <div class="radar-card-header">
          <div class="radar-meta-left">
            <span class="badge ${eventBadgeClass}">${eventLabel}</span>
            ${hasEmerging ? '<span class="badge badge-emerging">🔥 Emerging</span>' : ''}
            <span class="radar-source-name">${escapeHtml(item.source_name)}</span>
            <span class="radar-time">${formatRelativeTime(item.published_at_utc)}</span>
          </div>
          <div class="radar-meta-right">
            ${coverageBadge}
          </div>
        </div>

        <h3 class="radar-card-title">
          <a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">
            ${escapeHtml(item.title)}
          </a>
        </h3>

        ${item.takeaway ? `
          <div class="radar-takeaway">
            <span class="takeaway-label">💡 Key Insight:</span> ${escapeHtml(item.takeaway)}
          </div>
        ` : ''}

        <div class="radar-card-footer">
          <div class="radar-entities-row">
            ${entityPills}
          </div>
          ${primaryEntityId ? `
            <button class="btn btn-sm btn-secondary view-timeline-btn" data-entity-id="${primaryEntityId}">
              📈 Timeline & Updates
            </button>
          ` : ''}
        </div>
      </article>
    `;
  }).join('');

  stream.innerHTML = cardsHtml;

  // Attach event listeners for timeline buttons
  stream.querySelectorAll('.view-timeline-btn, .radar-entity-tag').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      const entId = el.getAttribute('data-entity-id');
      if (entId) {
        openEntityTimeline(entId);
      }
    });
  });
}

function renderEmergingEntitiesCards(entities, stream) {
  const cardsHtml = entities.map(e => `
    <article class="radar-card emerging-entity-card" data-entity-id="${e.id}">
      <div class="radar-card-header">
        <div class="radar-meta-left">
          <span class="badge badge-emerging">🔥 Emerging ${escapeHtml(e.type)}</span>
          <span class="radar-time">First seen ${formatRelativeTime(e.first_seen_utc)}</span>
        </div>
        <div class="radar-meta-right">
          <span class="radar-coverage-badge">Mentions: ${e.mention_count}</span>
        </div>
      </div>
      <h3 class="radar-card-title" style="font-size: 1.25rem;">
        ${escapeHtml(e.display_name)}
      </h3>
      <p style="color: var(--text-muted); font-size: 0.9rem; margin: 8px 0;">
        Rapidly emerging entity detected across independent sources.
      </p>
      <div class="radar-card-footer" style="justify-content: flex-end;">
        <button class="btn btn-sm btn-primary view-timeline-btn" data-entity-id="${e.id}">
          📈 View Chronological Timeline
        </button>
      </div>
    </article>
  `).join('');

  stream.innerHTML = cardsHtml;

  stream.querySelectorAll('.view-timeline-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      openEntityTimeline(btn.getAttribute('data-entity-id'));
    });
  });
}

// -------------------------------------------------------------
// Timeline Modal Dialog
// -------------------------------------------------------------

function setupTimelineModal() {
  const modal = document.getElementById('entityTimelineModal');
  const closeBtn = document.getElementById('timelineCloseBtn');
  if (!modal) return;

  if (closeBtn) {
    closeBtn.addEventListener('click', () => {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
    });
  }

  modal.addEventListener('click', (e) => {
    if (e.target === modal) {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
    }
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && modal.style.display === 'flex') {
      modal.style.display = 'none';
      modal.setAttribute('aria-hidden', 'true');
    }
  });
}

export async function openEntityTimeline(entityId) {
  const modal = document.getElementById('entityTimelineModal');
  const titleEl = document.getElementById('timelineEntityTitle');
  const metaEl = document.getElementById('timelineEntityMeta');
  const bodyEl = document.getElementById('timelineBody');
  if (!modal) return;

  modal.style.display = 'flex';
  modal.setAttribute('aria-hidden', 'false');

  bodyEl.innerHTML = `
    <div style="padding: 30px; text-align: center; color: var(--text-muted);">
      <div class="spinner" style="margin: 0 auto 10px;"></div>
      <p>Loading timeline of releases, benchmarks, and updates...</p>
    </div>
  `;

  try {
    const data = await api.getEntityTimeline(entityId);
    const ent = data.entity;
    const timeline = data.timeline || [];

    titleEl.textContent = ent.display_name;
    metaEl.innerHTML = `
      <span class="badge ${ent.is_emerging ? 'badge-emerging' : 'badge-general'}">${ent.is_emerging ? '🔥 Emerging ' : ''}${escapeHtml(ent.type)}</span>
      <span>First seen: ${formatRelativeTime(ent.first_seen_utc)}</span>
      <span>•</span>
      <span>Total Mentions: ${ent.mention_count}</span>
    `;

    if (timeline.length === 0) {
      bodyEl.innerHTML = `<p style="padding: 20px; color: var(--text-muted);">No timeline events recorded for this entity yet.</p>`;
      return;
    }

    const timelineHtml = timeline.map(item => {
      const safeUrl = isValidHttpUrl(item.url) ? item.url : '#';
      const isRel = item.event_type === 'model_release';
      const isUpd = item.event_type === 'model_update';
      const evBadge = isRel ? 'badge-release' : (isUpd ? 'badge-update' : 'badge-general');

      const siblingsHtml = (item.also_covered_by && item.also_covered_by.length > 0) ? `
        <div class="timeline-siblings">
          <span style="font-size: 0.8rem; color: var(--text-muted);">Also covered by:</span>
          ${item.also_covered_by.map(s => `
            <a href="${escapeHtml(isValidHttpUrl(s.url) ? s.url : '#')}" target="_blank" rel="noopener noreferrer" class="timeline-sibling-link">
              ${escapeHtml(s.source_name || 'Source')}
            </a>
          `).join(', ')}
        </div>
      ` : '';

      return `
        <div class="timeline-item">
          <div class="timeline-marker"></div>
          <div class="timeline-content">
            <div class="timeline-header">
              <span class="badge ${evBadge}">${escapeHtml(item.event_type || 'event')}</span>
              <span class="timeline-source">${escapeHtml(item.source_name || 'Unknown')}</span>
              <span class="timeline-date">${formatRelativeTime(item.published_at_utc)}</span>
            </div>
            <h4 class="timeline-title">
              <a href="${escapeHtml(safeUrl)}" target="_blank" rel="noopener noreferrer">
                ${escapeHtml(item.title)}
              </a>
            </h4>
            ${item.takeaway ? `<p class="timeline-takeaway">${escapeHtml(item.takeaway)}</p>` : ''}
            ${item.evidence ? `<blockquote class="timeline-evidence">"${escapeHtml(item.evidence)}"</blockquote>` : ''}
            ${siblingsHtml}
          </div>
        </div>
      `;
    }).join('');

    bodyEl.innerHTML = `<div class="timeline-flow">${timelineHtml}</div>`;

  } catch (err) {
    bodyEl.innerHTML = `
      <div style="padding: 20px; color: var(--color-danger);">
        <p>Failed to load entity timeline: ${escapeHtml(err.message)}</p>
      </div>
    `;
  }
}
