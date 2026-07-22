/**
 * upload-workspace.js
 * ---------------------------------------------------------------------
 * Enterprise Upload Workspace behavior: drag & drop, multi-file queue,
 * real upload progress, and the Recent Documents table — all wired to
 * the existing apps.documents REST API (no new endpoints introduced):
 *
 *   GET    /api/documents/supported-formats/
 *   POST   /api/documents/upload/
 *   GET    /api/documents/                  (search/status/extension filters)
 *   GET    /api/documents/{id}/status/
 *   DELETE /api/documents/{id}/
 *
 * fetch() is used for every call except the actual upload POST, which
 * uses XMLHttpRequest specifically because fetch() has no API for
 * reporting upload progress — XHR's `upload.onprogress` is the only
 * standard way to drive a real, live progress bar for a multipart POST.
 * ---------------------------------------------------------------------
 */
(function () {
  "use strict";

  const API_BASE = "/api/documents";
  const QUEUE_POLL_INTERVAL_MS = 2500;

  /** @type {Map<string, object>} keyed by a client-generated queue id */
  const queue = new Map();

  let supportedFormats = { allowed_extensions: [], max_upload_size_bytes: 50 * 1024 * 1024 };
  let documentsState = {
    results: [],
    count: 0,
    page: 1,
    pageSize: 20,
    search: "",
    status: "",
    extension: "",
    sortKey: "created_at",
    sortDirection: "desc",
  };
  let statusPollTimer = null;

  // -----------------------------------------------------------------
  // CSRF / fetch helpers
  // -----------------------------------------------------------------

  function getCsrfToken() {
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  async function apiFetch(path, options = {}) {
    const response = await fetch(`${API_BASE}${path}`, {
      credentials: "same-origin",
      headers: {
        "X-CSRFToken": getCsrfToken(),
        ...(options.headers || {}),
      },
      ...options,
    });

    if (!response.ok) {
      let detail = `Request failed with status ${response.status}`;
      try {
        const data = await response.json();
        detail = data.detail || data.file || JSON.stringify(data);
      } catch (_error) {
        /* response had no JSON body */
      }
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }

    if (response.status === 204) return null;
    return response.json();
  }

  function formatBytes(bytes) {
    if (!bytes) return "0 B";
    const units = ["B", "KB", "MB", "GB"];
    const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
    const value = bytes / 1024 ** exponent;
    return `${exponent === 0 ? value : value.toFixed(1)} ${units[exponent]}`;
  }

  function formatDate(isoString) {
    if (!isoString) return "—";
    const date = new Date(isoString);
    return date.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function escapeHtml(value) {
    const div = document.createElement("div");
    div.textContent = value;
    return div.innerHTML;
  }

  // -----------------------------------------------------------------
  // Supported formats
  // -----------------------------------------------------------------

  async function loadSupportedFormats() {
    try {
      supportedFormats = await apiFetch("/supported-formats/");
    } catch (error) {
      console.error("Failed to load supported formats:", error);
      return;
    }

    const hint = document.querySelector("[data-supported-formats-hint]");
    if (hint) {
      const formats = supportedFormats.allowed_extensions.map((ext) => ext.toUpperCase()).join(", ");
      hint.textContent = `Supports ${formats} — up to ${supportedFormats.max_upload_size_mb} MB`;
    }

    const maxSizeHint = document.querySelector("[data-max-file-size-hint]");
    if (maxSizeHint) {
      maxSizeHint.textContent = `Maximum file size: ${supportedFormats.max_upload_size_mb} MB`;
    }
  }

  function validateFileClientSide(file) {
    const extension = file.name.split(".").pop().toLowerCase();
    if (
      supportedFormats.allowed_extensions.length &&
      !supportedFormats.allowed_extensions.includes(extension)
    ) {
      const formats = supportedFormats.allowed_extensions.map((ext) => ext.toUpperCase()).join(", ");
      return `Unsupported file type ".${extension}". Supported formats: ${formats}.`;
    }

    if (file.size === 0) {
      return "This file is empty.";
    }

    if (
      supportedFormats.max_upload_size_bytes &&
      file.size > supportedFormats.max_upload_size_bytes
    ) {
      return `File is too large (${formatBytes(file.size)}). Maximum allowed size is ${supportedFormats.max_upload_size_mb} MB.`;
    }

    return null;
  }

  // -----------------------------------------------------------------
  // Upload queue (client-side session state)
  // -----------------------------------------------------------------

  function generateQueueId() {
    return `q_${Date.now()}_${Math.random().toString(36).slice(2, 9)}`;
  }

  function addFilesToQueue(fileList) {
    const existingNames = documentsState.results.map((doc) => doc.original_filename);

    Array.from(fileList).forEach((file) => {
      const queueId = generateQueueId();
      const validationError = validateFileClientSide(file);
      const isDuplicate = existingNames.includes(file.name);

      queue.set(queueId, {
        queueId,
        file,
        status: validationError ? "invalid" : "queued",
        progress: 0,
        error: validationError,
        isDuplicateWarning: !validationError && isDuplicate,
        documentId: null,
        startedAt: null,
      });
    });

    renderQueue();

    // Start uploads for every newly queued (valid) file, independently
    // and concurrently — one file's upload never blocks another.
    Array.from(queue.values())
      .filter((item) => item.status === "queued")
      .forEach(startUpload);
  }

  function removeFromQueue(queueId) {
    const item = queue.get(queueId);
    if (item && item.xhr) {
      item.xhr.abort();
    }
    queue.delete(queueId);
    renderQueue();
  }

  function retryUpload(queueId) {
    const item = queue.get(queueId);
    if (!item) return;
    item.status = "queued";
    item.progress = 0;
    item.error = null;
    renderQueue();
    startUpload(item);
  }

  function startUpload(item) {
    item.status = "uploading";
    item.startedAt = Date.now();
    renderQueue();

    const formData = new FormData();
    formData.append("file", item.file);

    const xhr = new XMLHttpRequest();
    item.xhr = xhr;

    xhr.open("POST", `${API_BASE}/upload/`, true);
    xhr.setRequestHeader("X-CSRFToken", getCsrfToken());

    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return;
      item.progress = Math.round((event.loaded / event.total) * 100);
      renderQueueItem(item);
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        const document_ = JSON.parse(xhr.responseText);
        item.status = "completed";
        item.progress = 100;
        item.documentId = document_.id;
        item.serverStatus = document_.status;
        renderQueueItem(item, { justCompleted: true });
        celebrateUploadComplete();
        refreshDocumentsTable();
        renderProcessingStatus(document_);
      } else {
        item.status = "failed";
        item.error = parseXhrError(xhr);
        renderQueueItem(item);
      }
    };

    xhr.onerror = () => {
      item.status = "failed";
      item.error = "Network error — please check your connection and retry.";
      renderQueueItem(item);
    };

    xhr.onabort = () => {
      // Item already removed from the queue by removeFromQueue(); no
      // further UI update needed.
    };

    xhr.send(formData);
  }

  function parseXhrError(xhr) {
    try {
      const data = JSON.parse(xhr.responseText);
      return data.file || data.detail || "Upload failed.";
    } catch (_error) {
      return `Upload failed with status ${xhr.status}.`;
    }
  }

  function estimateRemainingSeconds(item) {
    if (!item.startedAt || item.progress <= 0 || item.progress >= 100) return null;
    const elapsedMs = Date.now() - item.startedAt;
    const totalEstimatedMs = elapsedMs / (item.progress / 100);
    const remainingMs = Math.max(totalEstimatedMs - elapsedMs, 0);
    return Math.round(remainingMs / 1000);
  }

  function queueItemIconName(item) {
    if (item.status === "completed") return "check-circle";
    if (item.status === "failed" || item.status === "invalid") return "exclamation-triangle";
    return "document-text";
  }

  function renderQueue() {
    const list = document.querySelector("[data-upload-queue]");
    const emptyState = document.querySelector("[data-upload-queue-empty]");
    if (!list) return;

    const items = Array.from(queue.values());
    if (emptyState) {
      emptyState.style.display = items.length ? "none" : "";
    }

    list.querySelectorAll("[data-queue-item]").forEach((node) => node.remove());

    items.forEach((item) => {
      const node = buildQueueItemNode(item);
      list.appendChild(node);
    });
  }

  function buildQueueItemNode(item) {
    const li = document.createElement("li");
    li.dataset.queueItem = item.queueId;
    li.className = `upload-queue-item upload-queue-item--${item.status}`;
    li.innerHTML = queueItemInnerHtml(item);
    attachQueueItemHandlers(li, item);
    return li;
  }

  function renderQueueItem(item, { justCompleted = false } = {}) {
    const node = document.querySelector(`[data-queue-item="${item.queueId}"]`);
    if (!node) {
      renderQueue();
      return;
    }
    node.className = `upload-queue-item upload-queue-item--${item.status}`;
    node.innerHTML = queueItemInnerHtml(item);
    attachQueueItemHandlers(node, item);

    if (justCompleted) {
      node.classList.add("upload-queue-item--just-completed");
      window.setTimeout(() => node.classList.remove("upload-queue-item--just-completed"), 450);
    }
  }

  function queueItemInnerHtml(item) {
    const remaining = item.status === "uploading" ? estimateRemainingSeconds(item) : null;
    const metaParts = [formatBytes(item.file.size)];
    if (item.status === "uploading") {
      metaParts.push(`${item.progress}%`);
      if (remaining !== null) metaParts.push(`~${remaining}s remaining`);
    } else if (item.status === "completed") {
      metaParts.push("Ready for parsing");
    } else if (item.isDuplicateWarning) {
      metaParts.push("A file with this name already exists");
    }

    const showProgressBar = item.status === "uploading" || item.status === "completed";
    const showRetry = item.status === "failed";
    const showCancel = item.status === "uploading" || item.status === "queued";

    return `
      <span class="upload-queue-item__icon" data-icon-slot></span>
      <div class="upload-queue-item__body">
        <div class="upload-queue-item__name-row">
          <span class="upload-queue-item__name" title="${escapeHtml(item.file.name)}">${escapeHtml(item.file.name)}</span>
        </div>
        <p class="upload-queue-item__meta">${metaParts.join(" · ")}</p>
        ${item.error ? `<p class="upload-queue-item__error">${escapeHtml(item.error)}</p>` : ""}
        ${
          showProgressBar
            ? `<div class="upload-queue-item__progress-track"><div class="upload-queue-item__progress-fill" style="width:${item.progress}%"></div></div>`
            : ""
        }
      </div>
      <div class="upload-queue-item__actions">
        ${showRetry ? `<button type="button" class="upload-queue-item__action-btn" data-retry-btn aria-label="Retry upload"></button>` : ""}
        ${showCancel || showRetry ? `<button type="button" class="upload-queue-item__action-btn upload-queue-item__action-btn--danger" data-remove-btn aria-label="Remove"></button>` : ""}
      </div>
    `;
  }

  function attachQueueItemHandlers(node, item) {
    const iconSlot = node.querySelector("[data-icon-slot]");
    if (iconSlot) {
      renderIconInto(iconSlot, queueItemIconName(item));
    }

    const retryBtn = node.querySelector("[data-retry-btn]");
    if (retryBtn) {
      renderIconInto(retryBtn, "arrow-path");
      retryBtn.addEventListener("click", () => retryUpload(item.queueId));
    }

    const removeBtn = node.querySelector("[data-remove-btn]");
    if (removeBtn) {
      renderIconInto(removeBtn, "trash");
      removeBtn.addEventListener("click", () => removeFromQueue(item.queueId));
    }
  }

  // -----------------------------------------------------------------
  // Icon rendering (client-side mirror of the Heroicons used server-side
  // in templates/shared/_icon.html — only the subset this page needs)
  // -----------------------------------------------------------------

  const ICONS = {
    "document-text":
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 0 0-3.375-3.375h-1.5A1.125 1.125 0 0 1 13.5 7.125v-1.5a3.375 3.375 0 0 0-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M8.25 2.25H10.5m0 0V6m0-3.75c-3.108.02-5.65.257-7.5.75" /></svg>',
    "check-circle":
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M9 12.75 11.25 15 15 9.75M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z" /></svg>',
    "exclamation-triangle":
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126ZM12 15.75h.007v.008H12v-.008Z" /></svg>',
    "arrow-path":
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0 3.181 3.183a8.25 8.25 0 0 0 13.803-3.7M4.031 9.865a8.25 8.25 0 0 1 13.803-3.7l3.181 3.182m0-4.991v4.99" /></svg>',
    trash:
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 0 1-2.244 2.077H8.084a2.25 2.25 0 0 1-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 0 0-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 0 1 3.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 0 0-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 0 0-7.5 0" /></svg>',
    eye:
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M2.036 12.322a1.012 1.012 0 0 1 0-.639C3.423 7.51 7.36 4.5 12 4.5c4.638 0 8.573 3.007 9.963 7.178.07.207.07.431 0 .639C20.577 16.49 16.64 19.5 12 19.5c-4.638 0-8.573-3.007-9.963-7.178Z" /><path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" /></svg>',
    "arrow-down-tray":
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5m-13.5-6 4.5 4.5 4.5-4.5m-4.5 4.5V3" /></svg>',
    "arrow-up-tray":
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 0 0 5.25 21h13.5A2.25 2.25 0 0 0 21 18.75V16.5M16.5 7.5 12 3m0 0L7.5 7.5M12 3v13.5" /></svg>',
    "circle-stack":
      '<svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="1.5" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" d="M20.25 6.375c0 2.278-3.694 4.125-8.25 4.125S3.75 8.653 3.75 6.375m16.5 0c0-2.278-3.694-4.125-8.25-4.125S3.75 4.097 3.75 6.375m16.5 0v11.25c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125V6.375m16.5 0v3.75m-16.5-3.75v3.75m16.5 0v3.75C20.25 16.153 16.556 18 12 18s-8.25-1.847-8.25-4.125v-3.75m16.5 0c0 2.278-3.694 4.125-8.25 4.125s-8.25-1.847-8.25-4.125" /></svg>',
  };

  function renderIconInto(element, iconName) {
    element.innerHTML = ICONS[iconName] || "";
    const svg = element.querySelector("svg");
    if (svg) svg.setAttribute("aria-hidden", "true");
  }

  // -----------------------------------------------------------------
  // Processing status widget (implemented stages only)
  // -----------------------------------------------------------------

  // Only the stages this sprint's backend actually implements are
  // shown as real/live. Parsing onward are rendered as an explicit
  // "coming in a future sprint" upcoming group, per the requirement
  // not to imply Parser/Chunker/Embedding/ChromaDB/Knowledge Graph
  // integration exists yet.
  const IMPLEMENTED_STAGES = [
    { key: "uploaded", label: "Uploading", icon: "arrow-up-tray" },
    { key: "stored", label: "Saving File", icon: "circle-stack" },
    { key: "ready_for_parsing", label: "Ready for Parsing", icon: "check-circle" },
  ];

  function renderProcessingStatus(document_) {
    const wrapper = document.querySelector("[data-upload-processing]");
    const emptyState = document.querySelector("[data-upload-processing-empty]");
    const track = document.querySelector("[data-upload-pipeline-track]");
    if (!wrapper || !track) return;

    if (emptyState) emptyState.style.display = "none";
    track.hidden = false;
    track.innerHTML = "";

    const reachedIndex = IMPLEMENTED_STAGES.findIndex((stage) => stage.key === document_.status);

    IMPLEMENTED_STAGES.forEach((stage, index) => {
      const state = index < reachedIndex ? "complete" : index === reachedIndex ? "complete" : "pending";
      const stageEl = document.createElement("div");
      stageEl.className = `pipeline-stage pipeline-stage--${state}`;
      stageEl.innerHTML = `
        <div class="pipeline-stage__icon" data-icon-slot></div>
        <div class="mt-3 text-center">
          <p class="text-xs font-semibold text-slate-700 dark:text-slate-200 leading-tight">${stage.label}</p>
        </div>
      `;
      renderIconInto(stageEl.querySelector("[data-icon-slot]"), state === "complete" ? "check-circle" : stage.icon);
      track.appendChild(stageEl);

      if (index < IMPLEMENTED_STAGES.length - 1) {
        const connector = document.createElement("div");
        connector.className = `pipeline-connector${index < reachedIndex ? " is-filled" : ""}`;
        track.appendChild(connector);
      }
    });

    const upcomingNote = document.createElement("p");
    upcomingNote.className = "upload-processing__empty";
    upcomingNote.style.marginTop = "1rem";
    upcomingNote.textContent =
      "Parsing, chunking, embedding, and knowledge graph indexing will begin automatically in a future sprint.";
    track.appendChild(upcomingNote);
  }

  // -----------------------------------------------------------------
  // Recent Documents table
  // -----------------------------------------------------------------

  function buildListQueryString() {
    const params = new URLSearchParams();
    params.set("page", String(documentsState.page));
    if (documentsState.search) params.set("search", documentsState.search);
    if (documentsState.status) params.set("status", documentsState.status);
    if (documentsState.extension) params.set("extension", documentsState.extension);
    return params.toString();
  }

  async function refreshDocumentsTable() {
    try {
      const data = await apiFetch(`/?${buildListQueryString()}`);
      documentsState.results = sortResults(data.results || []);
      documentsState.count = data.count || 0;
      documentsState.hasNext = Boolean(data.next);
      documentsState.hasPrevious = Boolean(data.previous);
    } catch (error) {
      console.error("Failed to load documents:", error);
      documentsState.results = [];
      documentsState.count = 0;
    }
    renderDocumentsTable();
  }

  function sortResults(results) {
    const { sortKey, sortDirection } = documentsState;
    const sorted = [...results].sort((a, b) => {
      const left = a[sortKey];
      const right = b[sortKey];
      if (left === right) return 0;
      return left > right ? 1 : -1;
    });
    return sortDirection === "desc" ? sorted.reverse() : sorted;
  }

  function renderDocumentsTable() {
    const tbody = document.querySelector("[data-documents-table-body]");
    if (!tbody) return;

    tbody.innerHTML = "";

    if (!documentsState.results.length) {
      const row = document.createElement("tr");
      row.innerHTML = `<td colspan="6" class="upload-documents__empty">No documents match your filters.</td>`;
      tbody.appendChild(row);
    } else {
      documentsState.results.forEach((doc) => {
        tbody.appendChild(buildDocumentRow(doc));
      });
    }

    const pageInfo = document.querySelector("[data-documents-page-info]");
    if (pageInfo) {
      const totalPages = Math.max(1, Math.ceil(documentsState.count / documentsState.pageSize));
      pageInfo.textContent = `Page ${documentsState.page} of ${totalPages}`;
    }

    const prevBtn = document.querySelector("[data-documents-prev-page]");
    const nextBtn = document.querySelector("[data-documents-next-page]");
    if (prevBtn) prevBtn.disabled = !documentsState.hasPrevious;
    if (nextBtn) nextBtn.disabled = !documentsState.hasNext;
  }

  function buildDocumentRow(doc) {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td class="dash-table__doc-name">
        <span class="dash-table__doc-icon" data-icon-slot></span>
        ${escapeHtml(doc.original_filename)}
      </td>
      <td>${doc.extension.toUpperCase()}</td>
      <td class="text-right">${formatBytes(doc.file_size)}</td>
      <td class="text-slate-500 dark:text-slate-400">${formatDate(doc.created_at)}</td>
      <td data-status-slot></td>
      <td class="text-right">
        <div class="dash-table__actions">
          <button type="button" class="dash-table__action-btn" data-view-btn aria-label="View ${escapeHtml(doc.original_filename)}"></button>
          <button type="button" class="dash-table__action-btn" data-download-btn aria-label="Download ${escapeHtml(doc.original_filename)}"></button>
          <button type="button" class="dash-table__action-btn dash-table__action-btn--danger" data-delete-btn aria-label="Delete ${escapeHtml(doc.original_filename)}"></button>
        </div>
      </td>
    `;

    renderIconInto(row.querySelector("[data-icon-slot]"), "document-text");
    renderStatusBadgeInto(row.querySelector("[data-status-slot]"), doc.status, doc.status_display);

    const viewBtn = row.querySelector("[data-view-btn]");
    renderIconInto(viewBtn, "eye");
    viewBtn.addEventListener("click", () => {
      if (doc.download_url) window.open(doc.download_url, "_blank", "noopener");
    });

    const downloadBtn = row.querySelector("[data-download-btn]");
    renderIconInto(downloadBtn, "arrow-down-tray");
    downloadBtn.addEventListener("click", () => {
      if (doc.download_url) {
        const link = document.createElement("a");
        link.href = doc.download_url;
        link.download = doc.original_filename;
        link.click();
      }
    });

    const deleteBtn = row.querySelector("[data-delete-btn]");
    renderIconInto(deleteBtn, "trash");
    deleteBtn.addEventListener("click", () => handleDeleteDocument(doc));

    return row;
  }

  // Mirrors the class contract of
  // dashboard/components/_status_badge.html so client-rendered badges
  // are visually identical to server-rendered ones.
  const STATUS_BADGE_VARIANTS = {
    uploaded: "neutral",
    validating: "neutral",
    stored: "info",
    ready_for_parsing: "info",
    parsing: "warning",
    chunking: "info",
    embedding: "info",
    indexed: "success",
    failed: "danger",
  };

  function renderStatusBadgeInto(element, status, statusDisplay) {
    const variant = STATUS_BADGE_VARIANTS[status] || "neutral";
    element.innerHTML = `
      <span class="status-badge status-badge--${variant}">
        <span class="status-badge__dot"></span>${escapeHtml(statusDisplay || status)}
      </span>
    `;
  }

  async function handleDeleteDocument(doc) {
    const confirmed = window.confirm(`Delete "${doc.original_filename}"? This cannot be undone.`);
    if (!confirmed) return;

    try {
      await apiFetch(`/${doc.id}/`, { method: "DELETE" });
      refreshDocumentsTable();
    } catch (error) {
      window.alert(`Failed to delete document: ${error.message}`);
    }
  }

  // -----------------------------------------------------------------
  // Drag & drop wiring
  // -----------------------------------------------------------------

  function initDropzone() {
    const dropzone = document.querySelector("[data-dropzone]");
    const fileInput = document.querySelector("[data-file-input]");
    if (!dropzone || !fileInput) return;

    fileInput.addEventListener("change", () => {
      if (fileInput.files.length) {
        addFilesToQueue(fileInput.files);
        fileInput.value = "";
      }
    });

    dropzone.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        fileInput.click();
      }
    });

    let dragCounter = 0;

    ["dragenter", "dragover"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dragCounter += 1;
        dropzone.classList.add("is-dragover");
      });
    });

    ["dragleave", "dragend"].forEach((eventName) => {
      dropzone.addEventListener(eventName, (event) => {
        event.preventDefault();
        dragCounter = Math.max(0, dragCounter - 1);
        if (dragCounter === 0) dropzone.classList.remove("is-dragover");
      });
    });

    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dragCounter = 0;
      dropzone.classList.remove("is-dragover");
      if (event.dataTransfer && event.dataTransfer.files.length) {
        addFilesToQueue(event.dataTransfer.files);
      }
    });
  }

  // -----------------------------------------------------------------
  // Table toolbar wiring (search / filter / sort / pagination)
  // -----------------------------------------------------------------

  function initDocumentsToolbar() {
    const searchInput = document.querySelector("[data-documents-search]");
    const statusFilter = document.querySelector("[data-documents-status-filter]");
    const extensionFilter = document.querySelector("[data-documents-extension-filter]");
    const prevBtn = document.querySelector("[data-documents-prev-page]");
    const nextBtn = document.querySelector("[data-documents-next-page]");

    let searchDebounce = null;
    if (searchInput) {
      searchInput.addEventListener("input", () => {
        window.clearTimeout(searchDebounce);
        searchDebounce = window.setTimeout(() => {
          documentsState.search = searchInput.value.trim();
          documentsState.page = 1;
          refreshDocumentsTable();
        }, 300);
      });
    }

    if (statusFilter) {
      statusFilter.addEventListener("change", () => {
        documentsState.status = statusFilter.value;
        documentsState.page = 1;
        refreshDocumentsTable();
      });
    }

    if (extensionFilter) {
      extensionFilter.addEventListener("change", () => {
        documentsState.extension = extensionFilter.value;
        documentsState.page = 1;
        refreshDocumentsTable();
      });
    }

    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (documentsState.page > 1) {
          documentsState.page -= 1;
          refreshDocumentsTable();
        }
      });
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        documentsState.page += 1;
        refreshDocumentsTable();
      });
    }

    document.querySelectorAll("[data-sort-key]").forEach((header) => {
      header.addEventListener("click", () => {
        const key = header.dataset.sortKey;
        if (documentsState.sortKey === key) {
          documentsState.sortDirection = documentsState.sortDirection === "asc" ? "desc" : "asc";
        } else {
          documentsState.sortKey = key;
          documentsState.sortDirection = "asc";
        }
        documentsState.results = sortResults(documentsState.results);
        renderDocumentsTable();
      });
    });
  }

  // -----------------------------------------------------------------
  // Completion celebration (confetti)
  // -----------------------------------------------------------------

  function celebrateUploadComplete() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    const colors = ["#2563EB", "#06B6D4", "#7C3AED", "#10B981"];
    const pieceCount = 24;

    for (let i = 0; i < pieceCount; i += 1) {
      const piece = document.createElement("div");
      piece.className = "confetti-piece";
      piece.style.left = `${Math.random() * 100}vw`;
      piece.style.backgroundColor = colors[i % colors.length];
      document.body.appendChild(piece);

      if (typeof gsap !== "undefined") {
        gsap.to(piece, {
          y: window.innerHeight + 40,
          x: (Math.random() - 0.5) * 160,
          rotation: Math.random() * 360,
          opacity: 0,
          duration: 1.4 + Math.random() * 0.6,
          ease: "power1.in",
          onComplete: () => piece.remove(),
        });
      } else {
        window.setTimeout(() => piece.remove(), 1500);
      }
    }
  }

  // -----------------------------------------------------------------
  // Background status polling for documents still mid-pipeline
  // -----------------------------------------------------------------

  function startStatusPolling() {
    statusPollTimer = window.setInterval(async () => {
      const inProgress = documentsState.results.filter(
        (doc) => !["failed"].includes(doc.status)
      );
      if (!inProgress.length) return;
      refreshDocumentsTable();
    }, QUEUE_POLL_INTERVAL_MS);
  }

  // -----------------------------------------------------------------
  // Init
  // -----------------------------------------------------------------

  function init() {
    initDropzone();
    initDocumentsToolbar();
    loadSupportedFormats();
    refreshDocumentsTable();
    startStatusPolling();

    window.addEventListener("beforeunload", () => {
      if (statusPollTimer) window.clearInterval(statusPollTimer);
    });
  }

  document.addEventListener("DOMContentLoaded", init);
})();
