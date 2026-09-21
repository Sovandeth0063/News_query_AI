/**
 * API Service: Centralized HTTP client with AbortController, Error/429 Handling,
 * and Mock Mode support.
 */

import {
  mockArticles,
  mockPapers,
  mockDigest,
  mockSources,
  mockChatResponse
} from './fixtures.js';

const isMockMode = new URLSearchParams(window.location.search).get('mock') === '1' || window.__USE_MOCK_API__ === true;

export class ApiError extends Error {
  constructor(message, status = 0, data = null) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request(url, options = {}) {
  const { signal, ...restOptions } = options;
  try {
    const res = await fetch(url, {
      ...restOptions,
      signal,
      headers: {
        'Accept': 'application/json',
        ...(restOptions.headers || {})
      }
    });

    if (!res.ok) {
      let errBody = null;
      try {
        errBody = await res.json();
      } catch (e) {
        // Not JSON
      }

      if (res.status === 429) {
        throw new ApiError('AI service rate limit exceeded. Please wait a moment before trying again.', 429, errBody);
      }
      if (res.status === 409) {
        throw new ApiError('A sync is already in progress.', 409, errBody);
      }
      const msg = (errBody && errBody.detail) ? errBody.detail : `Request failed (${res.status} ${res.statusText})`;
      throw new ApiError(msg, res.status, errBody);
    }

    return await res.json();
  } catch (err) {
    if (err.name === 'AbortError') {
      throw err; // Allow caller to ignore aborted requests
    }
    if (err instanceof ApiError) {
      throw err;
    }
    throw new ApiError(err.message || 'Network error connecting to backend.', 0);
  }
}

export const api = {
  async getFeed({ category, search, sort = 'score', limit = 50, offset = 0, signal } = {}) {
    if (isMockMode) {
      let items = [...mockArticles];
      if (category && category !== 'ALL') {
        items = items.filter(a => a.category === category);
      }
      if (search && search.trim()) {
        const q = search.toLowerCase();
        items = items.filter(a => a.title.toLowerCase().includes(q) || a.summary.toLowerCase().includes(q));
      }
      return { articles: items.slice(offset, offset + limit), count: items.length };
    }

    const params = new URLSearchParams();
    if (category && category !== 'ALL') params.set('category', category);
    if (search && search.trim()) params.set('search', search.trim());
    if (sort) params.set('sort', sort);
    params.set('limit', String(limit));
    params.set('offset', String(offset));

    return request(`/api/feed?${params.toString()}`, { signal });
  },

  async getSidebarData({ signal } = {}) {
    if (isMockMode) {
      return {
        top_today: mockArticles.slice(0, 3),
        topic_counts: [
          { tag: 'LLMs', count: 12 },
          { tag: 'MLOps', count: 5 },
          { tag: 'Data Eng', count: 3 },
          { tag: 'PyTorch', count: 3 },
          { tag: 'Cloud', count: 2 }
        ],
        digest_preview: {
          digest_date: new Date().toISOString().slice(0, 10),
          snippet: 'Major breakthroughs in open-weights reasoning models and distributed GPU training frameworks highlight today\'s AI intelligence briefing.'
        }
      };
    }
    return request('/api/sidebar', { signal });
  },

  async getPapers({ search, limit = 50, offset = 0, signal } = {}) {
    if (isMockMode) {
      let items = [...mockPapers];
      if (search && search.trim()) {
        const q = search.toLowerCase();
        items = items.filter(p => p.title.toLowerCase().includes(q) || p.summary.toLowerCase().includes(q));
      }
      return { papers: items.slice(offset, offset + limit), count: items.length };
    }

    const params = new URLSearchParams();
    if (search && search.trim()) params.set('search', search.trim());
    params.set('limit', String(limit));
    params.set('offset', String(offset));

    return request(`/api/papers?${params.toString()}`, { signal });
  },

  async getArticleDetail(articleId, { signal } = {}) {
    if (isMockMode) {
      const art = mockArticles.find(a => a.id === articleId) || mockPapers.find(p => p.id === articleId);
      if (!art) throw new ApiError('Article not found', 404);
      return {
        article: art,
        siblings: art.cluster_id ? mockArticles.filter(a => a.cluster_id === art.cluster_id && a.id !== art.id) : []
      };
    }
    return request(`/api/articles/${encodeURIComponent(articleId)}`, { signal });
  },

  async setArticleRead(articleId, isRead) {
    if (isMockMode) return { status: 'ok', article_id: articleId, is_read: isRead };
    return request(`/api/articles/${encodeURIComponent(articleId)}/read`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_read: isRead })
    });
  },

  async setArticleBookmark(articleId, isBookmarked) {
    if (isMockMode) return { status: 'ok', article_id: articleId, is_bookmarked: isBookmarked };
    return request(`/api/articles/${encodeURIComponent(articleId)}/bookmark`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_bookmarked: isBookmarked })
    });
  },

  async getDigest(date = null, { signal } = {}) {
    if (isMockMode) return mockDigest;
    const url = date ? `/api/digest?date=${encodeURIComponent(date)}` : '/api/digest';
    return request(url, { signal });
  },

  async generateDigest(date = null, { signal } = {}) {
    if (isMockMode) return mockDigest;
    const url = date ? `/api/digest/generate?date=${encodeURIComponent(date)}` : '/api/digest/generate';
    return request(url, { method: 'POST', signal });
  },

  async chatWithAi(question, history = [], { signal } = {}) {
    if (isMockMode) {
      await new Promise(r => setTimeout(r, 600)); // Simulate typing latency
      return mockChatResponse;
    }
    return request('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, history }),
      signal
    });
  },

  async triggerSync() {
    if (isMockMode) return { status: 'started', run_id: 'mock_run_' + Date.now() };
    return request('/api/sync', { method: 'POST' });
  },

  async getSyncStatus(runId) {
    if (isMockMode) return { status: 'completed', percent: 100, message: 'Ingestion completed' };
    return request(`/api/sync/${encodeURIComponent(runId)}`);
  },

  async getSources({ signal } = {}) {
    if (isMockMode) return { sources: mockSources };
    return request('/api/sources', { signal });
  },

  async getRadar({ days = 7, event_type = null, limit = 50, offset = 0, signal } = {}) {
    const params = new URLSearchParams();
    params.set('days', String(days));
    if (event_type) params.set('event_type', event_type);
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    return request(`/api/radar?${params.toString()}`, { signal });
  },

  async getEntities({ emerging = null, type = null, q = null, limit = 50, offset = 0, signal } = {}) {
    const params = new URLSearchParams();
    if (emerging !== null && emerging !== undefined) params.set('emerging', String(emerging));
    if (type) params.set('type', type);
    if (q && q.trim()) params.set('q', q.trim());
    params.set('limit', String(limit));
    params.set('offset', String(offset));
    return request(`/api/entities?${params.toString()}`, { signal });
  },

  async getEntityDetail(entityId, { signal } = {}) {
    return request(`/api/entities/${encodeURIComponent(entityId)}`, { signal });
  },

  async getEntityTimeline(entityId, { signal } = {}) {
    return request(`/api/entities/${encodeURIComponent(entityId)}/timeline`, { signal });
  },

  async reprocessRadar(days = 7) {
    return request(`/api/radar/reprocess?days=${encodeURIComponent(days)}`, { method: 'POST' });
  }
};
