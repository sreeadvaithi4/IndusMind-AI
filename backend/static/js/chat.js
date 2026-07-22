/**
 * IndusMind AI — Chat Interface JavaScript
 *
 * Handles:
 * - Message submission via /api/query/
 * - Structured AI response rendering (citations, confidence, related, followups)
 * - Auto-scroll, typing indicator, textarea auto-resize
 * - Session ID management for conversation memory
 * - Suggestion chips and follow-up questions
 * - Error handling and graceful degradation
 */

(function () {
  "use strict";

  // ---------------------------------------------------------------------------
  // State
  // ---------------------------------------------------------------------------
  let sessionId = "session_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
  let isProcessing = false;

  // ---------------------------------------------------------------------------
  // DOM elements
  // ---------------------------------------------------------------------------
  const chatMessages = document.getElementById("chatMessages");
  const chatForm = document.getElementById("chatForm");
  const chatInput = document.getElementById("chatInput");
  const sendBtn = document.getElementById("sendBtn");
  const typingIndicator = document.getElementById("typingIndicator");
  const welcomeMessage = document.getElementById("welcomeMessage");
  const newChatBtn = document.getElementById("newChatBtn");
  const toggleSidebarBtn = document.getElementById("toggleSidebarBtn");
  const chatSidebar = document.getElementById("chatSidebar");

  // ---------------------------------------------------------------------------
  // CSRF
  // ---------------------------------------------------------------------------
  function getCookie(name) {
    const cookies = document.cookie.split(";");
    for (let c of cookies) {
      c = c.trim();
      if (c.startsWith(name + "=")) return decodeURIComponent(c.substring(name.length + 1));
    }
    return null;
  }

  function getCSRFToken() {
    return getCookie("csrftoken") || "";
  }

  // ---------------------------------------------------------------------------
  // API
  // ---------------------------------------------------------------------------
  async function sendQuery(query) {
    const response = await fetch("/api/query/", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCSRFToken(),
      },
      body: JSON.stringify({ query, session_id: sessionId }),
    });

    if (!response.ok) {
      const text = await response.text();
      throw new Error(`API error ${response.status}: ${text}`);
    }

    return response.json();
  }

  // ---------------------------------------------------------------------------
  // Message rendering
  // ---------------------------------------------------------------------------
  function addUserMessage(text) {
    if (welcomeMessage) welcomeMessage.classList.add("hidden");

    const msg = document.createElement("div");
    msg.className = "message message-user";
    msg.innerHTML = `
      <div class="message-avatar">You</div>
      <div class="message-content">${escapeHtml(text)}</div>
    `;
    chatMessages.appendChild(msg);
    scrollToBottom();
  }

  function addAssistantMessage(response) {
    const msg = document.createElement("div");
    msg.className = "message message-assistant";

    let html = `<div class="message-avatar">AI</div><div class="message-content">`;

    // Main answer
    html += `<div class="answer-text">${renderMarkdown(response.answer || "No response generated.")}</div>`;

    // Confidence badge
    if (response.confidence > 0) {
      const pct = Math.round(response.confidence * 100);
      const level = pct >= 70 ? "high" : pct >= 40 ? "medium" : "low";
      html += `<div class="response-section">
        <div class="response-section-title">Confidence</div>
        <span class="confidence-badge confidence-${level}">${pct}%</span>
      </div>`;
    }

    // Citations
    if (response.citations && response.citations.length > 0) {
      html += `<div class="response-section">
        <div class="response-section-title">Sources</div>
        <div>${response.citations.map((c, i) => renderCitation(c, i + 1)).join("")}</div>
      </div>`;
    }

    // Related Equipment
    if (response.related_equipment && response.related_equipment.length > 0) {
      html += `<div class="response-section">
        <div class="response-section-title">Related Equipment</div>
        <div>${response.related_equipment.map(e => `<span class="related-tag related-tag-equipment">${escapeHtml(e)}</span>`).join("")}</div>
      </div>`;
    }

    // Related Drawings
    if (response.drawing_references && response.drawing_references.length > 0) {
      html += `<div class="response-section">
        <div class="response-section-title">Related Drawings</div>
        <div>${response.drawing_references.map(d => `<span class="related-tag related-tag-drawing">${escapeHtml(d)}</span>`).join("")}</div>
      </div>`;
    }

    // Knowledge Graph
    if (response.knowledge_graph_references && response.knowledge_graph_references.length > 0) {
      html += `<div class="response-section">
        <div class="response-section-title">Knowledge Graph</div>
        <div>${response.knowledge_graph_references.slice(0, 5).map(k => `<span class="related-tag related-tag-kg">${escapeHtml(k)}</span>`).join("")}</div>
      </div>`;
    }

    // Related Documents
    if (response.related_documents && response.related_documents.length > 0) {
      html += `<div class="response-section">
        <div class="response-section-title">Related Documents</div>
        <div>${response.related_documents.slice(0, 5).map(d => `<span class="citation-card">${escapeHtml(d.slice(0, 12))}...</span>`).join("")}</div>
      </div>`;
    }

    // Suggested Follow-ups
    if (response.suggested_followups && response.suggested_followups.length > 0) {
      html += `<div class="response-section">
        <div class="response-section-title">Suggested Follow-ups</div>
        <div>${response.suggested_followups.map(q => `<button class="followup-btn" data-query="${escapeAttr(q)}">${escapeHtml(q)}</button>`).join("")}</div>
      </div>`;
    }

    html += `</div>`;
    msg.innerHTML = html;
    chatMessages.appendChild(msg);

    // Attach follow-up click handlers
    msg.querySelectorAll(".followup-btn").forEach(btn => {
      btn.addEventListener("click", () => handleSubmit(btn.dataset.query));
    });

    scrollToBottom();
  }

  function addErrorMessage(error) {
    const msg = document.createElement("div");
    msg.className = "message message-assistant";
    msg.innerHTML = `
      <div class="message-avatar">AI</div>
      <div class="message-content" style="border-color: #fecaca;">
        <p class="text-red-600 dark:text-red-400 text-sm">⚠️ ${escapeHtml(error)}</p>
        <p class="text-xs text-slate-500 mt-1">Please try again or rephrase your question.</p>
      </div>
    `;
    chatMessages.appendChild(msg);
    scrollToBottom();
  }

  function renderCitation(citation, index) {
    const parts = [];
    if (citation.source_type) parts.push(citation.source_type);
    if (citation.document_id) parts.push(citation.document_id.slice(0, 8));
    if (citation.page_number) parts.push(`p.${citation.page_number}`);
    const label = parts.length > 0 ? parts.join(" · ") : `Source ${index}`;
    return `<span class="citation-card">[${index}] ${escapeHtml(label)}</span>`;
  }

  // ---------------------------------------------------------------------------
  // Markdown rendering (lightweight)
  // ---------------------------------------------------------------------------
  function renderMarkdown(text) {
    if (!text) return "";
    let html = escapeHtml(text);
    // Code blocks
    html = html.replace(/```([\s\S]*?)```/g, "<pre><code>$1</code></pre>");
    // Inline code
    html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
    // Bold
    html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
    // Italic
    html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
    // Headings
    html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
    html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
    html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
    // Bullet lists
    html = html.replace(/^[\-\*] (.+)$/gm, "<li>$1</li>");
    html = html.replace(/(<li>.*<\/li>\n?)+/g, "<ul>$&</ul>");
    // Numbered lists
    html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");
    // Line breaks
    html = html.replace(/\n/g, "<br>");
    // Clean up double <br> in lists
    html = html.replace(/<br><li>/g, "<li>");
    return html;
  }

  // ---------------------------------------------------------------------------
  // Utilities
  // ---------------------------------------------------------------------------
  function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
  }

  function escapeAttr(text) {
    return text.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }

  function scrollToBottom() {
    requestAnimationFrame(() => {
      chatMessages.scrollTop = chatMessages.scrollHeight;
    });
  }

  function showTyping() {
    typingIndicator.classList.remove("hidden");
    scrollToBottom();
  }

  function hideTyping() {
    typingIndicator.classList.add("hidden");
  }

  function setProcessing(state) {
    isProcessing = state;
    sendBtn.disabled = state || !chatInput.value.trim();
    if (state) showTyping(); else hideTyping();
  }

  // ---------------------------------------------------------------------------
  // Event handlers
  // ---------------------------------------------------------------------------
  async function handleSubmit(query) {
    if (!query || !query.trim() || isProcessing) return;

    const text = query.trim();
    chatInput.value = "";
    chatInput.style.height = "auto";
    sendBtn.disabled = true;

    addUserMessage(text);
    setProcessing(true);

    try {
      const response = await sendQuery(text);
      addAssistantMessage(response);
    } catch (err) {
      addErrorMessage(err.message || "Failed to get response. Please try again.");
    } finally {
      setProcessing(false);
    }
  }

  chatForm.addEventListener("submit", (e) => {
    e.preventDefault();
    handleSubmit(chatInput.value);
  });

  // Auto-resize textarea
  chatInput.addEventListener("input", () => {
    chatInput.style.height = "auto";
    chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + "px";
    sendBtn.disabled = !chatInput.value.trim() || isProcessing;
  });

  // Enter to send (Shift+Enter for newline)
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(chatInput.value);
    }
  });

  // Suggestion chips
  document.querySelectorAll(".suggestion-chip").forEach(chip => {
    chip.addEventListener("click", () => handleSubmit(chip.dataset.query));
  });

  // New conversation
  newChatBtn.addEventListener("click", () => {
    sessionId = "session_" + Date.now() + "_" + Math.random().toString(36).slice(2, 8);
    chatMessages.innerHTML = "";
    if (welcomeMessage) {
      welcomeMessage.classList.remove("hidden");
      chatMessages.appendChild(welcomeMessage);
    }
  });

  // Mobile sidebar toggle
  if (toggleSidebarBtn) {
    toggleSidebarBtn.addEventListener("click", () => {
      chatSidebar.classList.toggle("open");
    });
  }
})();
