/**
 * Ask AI Controller: Intelligence Chat with Typing Indicator, Citation Parser,
 * Collapsible Sources, Quota Locks, and Suggested Prompt Pills.
 */

import { api, ApiError } from './api.js';
import { escapeHtml, isValidHttpUrl } from './utils.js';
import { showToast } from './toast.js';

let conversationHistory = [];
let isQueryRunning = false;
let abortCtrl = null;
let initialized = false;

export function initChat() {
  if (initialized) return;
  initialized = true;

  bindEvents();
}

function bindEvents() {
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSendBtn');

  if (sendBtn) {
    sendBtn.addEventListener('click', () => submitQuestion());
  }

  if (input) {
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitQuestion();
      }
    });
  }

  // Suggested prompt pills on empty state
  const pills = document.querySelectorAll('.chat-suggestion-pill');
  pills.forEach(pill => {
    pill.addEventListener('click', () => {
      const q = pill.textContent.trim();
      if (!input) return;
      if (q.includes('___')) {
        input.value = q.replace('___', '').trim() + ' ';
        input.focus();
      } else {
        input.value = q;
        submitQuestion();
      }
    });
  });
}

export function focusChatInput() {
  const input = document.getElementById('chatInput');
  if (input) {
    setTimeout(() => input.focus(), 100);
  }
}

async function submitQuestion() {
  const input = document.getElementById('chatInput');
  const sendBtn = document.getElementById('chatSendBtn');
  const messagesContainer = document.getElementById('chatMessages');
  const emptyState = document.getElementById('chatEmptyState');

  if (!input || isQueryRunning) return;
  const question = input.value.trim();
  if (!question) return;

  // Clear input & lock UI to protect quota
  input.value = '';
  isQueryRunning = true;
  input.disabled = true;
  sendBtn.disabled = true;

  if (emptyState) emptyState.style.display = 'none';

  // Append user bubble
  appendUserMessage(messagesContainer, question);
  conversationHistory.push({ role: 'user', content: question });

  // Append typing indicator
  const typingIndicator = appendTypingIndicator(messagesContainer);
  scrollToBottom(messagesContainer);

  if (abortCtrl) abortCtrl.abort();
  abortCtrl = new AbortController();

  try {
    const data = await api.chatWithAi(question, conversationHistory, { signal: abortCtrl.signal });

    // Remove typing indicator
    if (typingIndicator.parentNode) {
      typingIndicator.parentNode.removeChild(typingIndicator);
    }

    const answer = data.answer || 'No response generated.';
    const modelUsed = data.model_used || 'Gemini 3.5 Flash';
    const sources = data.sources || [];

    appendAiMessage(messagesContainer, answer, sources, modelUsed);
    conversationHistory.push({ role: 'model', content: answer });

  } catch (err) {
    if (typingIndicator.parentNode) {
      typingIndicator.parentNode.removeChild(typingIndicator);
    }

    if (err.name === 'AbortError') return;

    if (err instanceof ApiError && err.status === 429) {
      appendErrorMessage(messagesContainer, 'Rate limit exceeded. The AI quota is currently constrained; please try again in a few moments.');
      showToast('Rate limit reached', 'warning');
    } else {
      appendErrorMessage(messagesContainer, `Error: ${err.message}`);
    }
  } finally {
    isQueryRunning = false;
    input.disabled = false;
    sendBtn.disabled = false;
    input.focus();
    scrollToBottom(messagesContainer);
  }
}

function appendUserMessage(container, text) {
  const bubble = document.createElement('div');
  bubble.className = 'chat-message message-user';
  bubble.innerHTML = `
    <div class="message-bubble">
      <p>${escapeHtml(text)}</p>
    </div>
  `;
  container.appendChild(bubble);
}

function appendTypingIndicator(container) {
  const indicator = document.createElement('div');
  indicator.className = 'chat-message message-ai message-typing';
  indicator.innerHTML = `
    <div class="message-avatar">⚡</div>
    <div class="message-bubble typing-bubble">
      <div class="typing-dots">
        <span></span><span></span><span></span>
      </div>
      <span class="typing-text">Analyzing news articles…</span>
    </div>
  `;
  container.appendChild(indicator);
  return indicator;
}

function appendAiMessage(container, answerText, sources, modelUsed) {
  const bubble = document.createElement('div');
  bubble.className = 'chat-message message-ai';

  // Format citations safely: replace [1], [2] with validated links
  let formatted = escapeHtml(answerText);
  if (Array.isArray(sources) && sources.length > 0) {
    formatted = formatted.replace(/\[(\d+)\]/g, (match, num) => {
      const idx = parseInt(num, 10);
      const src = sources.find(s => s.index === idx);
      if (src && isValidHttpUrl(src.url)) {
        return `<a href="${escapeHtml(src.url)}" target="_blank" rel="noopener noreferrer" class="citation-link" title="${escapeHtml(src.title)}">[${idx}]</a>`;
      }
      return match;
    });
  }

  // Format paragraphs
  const paragraphs = formatted.split(/\n{2,}|\n/).filter(p => p.trim().length > 0);
  const formattedHtml = paragraphs.map(p => `<p>${p}</p>`).join('');

  // Sources collapsible panel
  let sourcesHtml = '';
  if (Array.isArray(sources) && sources.length > 0) {
    const validSources = sources.filter(s => isValidHttpUrl(s.url));
    if (validSources.length > 0) {
      sourcesHtml = `
        <details class="chat-sources-accordion">
          <summary>Cited Sources (${validSources.length})</summary>
          <div class="chat-sources-list">
            ${validSources.map(s => `
              <div class="chat-source-item">
                <span class="citation-badge">[${s.index}]</span>
                <a href="${escapeHtml(s.url)}" target="_blank" rel="noopener noreferrer" class="chat-source-link">
                  ${escapeHtml(s.title)}
                </a>
                <span class="chat-source-name">(${escapeHtml(s.source || 'Source')})</span>
              </div>
            `).join('')}
          </div>
        </details>
      `;
    }
  }

  bubble.innerHTML = `
    <div class="message-avatar" aria-hidden="true">⚡</div>
    <div class="message-body">
      <div class="message-bubble">
        <div class="ai-text-content">${formattedHtml}</div>
        ${sourcesHtml}
      </div>
      <div class="message-meta-footer">
        <span class="ai-model-tag">${escapeHtml(modelUsed)}</span>
      </div>
    </div>
  `;

  container.appendChild(bubble);
}

function appendErrorMessage(container, msg) {
  const bubble = document.createElement('div');
  bubble.className = 'chat-message message-ai message-error';
  bubble.innerHTML = `
    <div class="message-avatar" aria-hidden="true">⚠️</div>
    <div class="message-bubble">
      <p style="color: var(--danger); font-weight: 500;">${escapeHtml(msg)}</p>
    </div>
  `;
  container.appendChild(bubble);
}

function scrollToBottom(container) {
  if (container) {
    container.scrollTop = container.scrollHeight;
  }
}
