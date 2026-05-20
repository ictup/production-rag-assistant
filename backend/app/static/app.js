const state = {
  apiKey: localStorage.getItem("rag.apiKey") || "dev-key",
  workspaceId: localStorage.getItem("rag.workspaceId") || "public",
  sessionId: localStorage.getItem("rag.sessionId") || "",
  sessions: [],
  documents: [],
  admin: {
    workspaces: [],
    logs: [],
    workspaceLimit: 20,
    workspaceOffset: 0,
    logLimit: 5,
    logOffset: 0,
    workspaceFilter: "all",
    workspaceSearch: "",
    selectedWorkspaceIds: new Set(),
    filters: {
      requestId: "",
      sessionId: "",
      citationValid: "",
      refusalOnly: false,
    },
  },
  sending: false,
};

const els = {
  apiKey: document.querySelector("#api-key"),
  workspaceId: document.querySelector("#workspace-id"),
  workspaceArchiveBanner: document.querySelector("#workspace-archive-banner"),
  newSession: document.querySelector("#new-session"),
  reloadSessions: document.querySelector("#reload-sessions"),
  sessionList: document.querySelector("#session-list"),
  sessionTitle: document.querySelector("#session-title"),
  status: document.querySelector("#status"),
  messages: document.querySelector("#messages"),
  chatForm: document.querySelector("#chat-form"),
  question: document.querySelector("#question"),
  send: document.querySelector("#send"),
  reloadDocuments: document.querySelector("#reload-documents"),
  documentForm: document.querySelector("#document-form"),
  documentSourceUri: document.querySelector("#document-source-uri"),
  documentTitle: document.querySelector("#document-title"),
  documentFile: document.querySelector("#document-file"),
  documentMarkdown: document.querySelector("#document-markdown"),
  uploadDocument: document.querySelector("#upload-document"),
  reindexSourceUri: document.querySelector("#reindex-source-uri"),
  reindexDryRun: document.querySelector("#reindex-dry-run"),
  reindexWrite: document.querySelector("#reindex-write"),
  documentStatus: document.querySelector("#document-status"),
  documentList: document.querySelector("#document-list"),
  reloadAdmin: document.querySelector("#reload-admin"),
  adminStatus: document.querySelector("#admin-status"),
  adminWorkspaceCount: document.querySelector("#admin-workspace-count"),
  adminLogCount: document.querySelector("#admin-log-count"),
  adminWorkspaceForm: document.querySelector("#admin-workspace-form"),
  adminWorkspaceId: document.querySelector("#admin-workspace-id"),
  adminWorkspaceName: document.querySelector("#admin-workspace-name"),
  adminWorkspaceDescription: document.querySelector("#admin-workspace-description"),
  createAdminWorkspace: document.querySelector("#create-admin-workspace"),
  adminWorkspaceEditForm: document.querySelector("#admin-workspace-edit-form"),
  adminEditWorkspaceId: document.querySelector("#admin-edit-workspace-id"),
  adminEditWorkspaceName: document.querySelector("#admin-edit-workspace-name"),
  adminEditWorkspaceDescription: document.querySelector(
    "#admin-edit-workspace-description",
  ),
  adminEditWorkspaceMetadata: document.querySelector("#admin-edit-workspace-metadata"),
  adminArchiveWorkspaceReason: document.querySelector(
    "#admin-archive-workspace-reason",
  ),
  saveAdminWorkspace: document.querySelector("#save-admin-workspace"),
  archiveAdminWorkspace: document.querySelector("#archive-admin-workspace"),
  restoreAdminWorkspace: document.querySelector("#restore-admin-workspace"),
  adminFilterForm: document.querySelector("#admin-filter-form"),
  adminRequestId: document.querySelector("#admin-request-id"),
  adminSessionId: document.querySelector("#admin-session-id"),
  adminCitationValid: document.querySelector("#admin-citation-valid"),
  adminRefusalOnly: document.querySelector("#admin-refusal-only"),
  clearAdminFilters: document.querySelector("#clear-admin-filters"),
  exportAdminJsonl: document.querySelector("#export-admin-jsonl"),
  exportAdminCsv: document.querySelector("#export-admin-csv"),
  adminWorkspaceFilterAll: document.querySelector("#admin-workspace-filter-all"),
  adminWorkspaceFilterActive: document.querySelector(
    "#admin-workspace-filter-active",
  ),
  adminWorkspaceFilterArchived: document.querySelector(
    "#admin-workspace-filter-archived",
  ),
  adminWorkspaceFilterSummary: document.querySelector(
    "#admin-workspace-filter-summary",
  ),
  adminPrevWorkspaces: document.querySelector("#admin-prev-workspaces"),
  adminNextWorkspaces: document.querySelector("#admin-next-workspaces"),
  adminWorkspacePageInfo: document.querySelector("#admin-workspace-page-info"),
  adminWorkspaceSearchForm: document.querySelector("#admin-workspace-search-form"),
  adminWorkspaceSearch: document.querySelector("#admin-workspace-search"),
  adminClearWorkspaceSearch: document.querySelector(
    "#admin-clear-workspace-search",
  ),
  adminWorkspaceSelectionSummary: document.querySelector(
    "#admin-workspace-selection-summary",
  ),
  adminBulkArchiveWorkspaces: document.querySelector(
    "#admin-bulk-archive-workspaces",
  ),
  adminBulkRestoreWorkspaces: document.querySelector(
    "#admin-bulk-restore-workspaces",
  ),
  adminClearWorkspaceSelection: document.querySelector(
    "#admin-clear-workspace-selection",
  ),
  adminWorkspaceList: document.querySelector("#admin-workspace-list"),
  adminPrevLogs: document.querySelector("#admin-prev-logs"),
  adminNextLogs: document.querySelector("#admin-next-logs"),
  adminPageInfo: document.querySelector("#admin-page-info"),
  adminLogList: document.querySelector("#admin-log-list"),
};

function init() {
  els.apiKey.value = state.apiKey;
  els.workspaceId.value = state.workspaceId;
  bindEvents();
  renderEmptyMessages();
  void loadSessions();
  void loadDocuments();
  void loadAdminOverview();
}

function bindEvents() {
  els.apiKey.addEventListener("input", () => {
    state.apiKey = els.apiKey.value.trim();
    localStorage.setItem("rag.apiKey", state.apiKey);
  });

  els.workspaceId.addEventListener("input", () => {
    state.workspaceId = els.workspaceId.value.trim() || "public";
    localStorage.setItem("rag.workspaceId", state.workspaceId);
    syncWorkspaceWriteGuards();
  });

  els.workspaceId.addEventListener("change", () => {
    state.admin.logOffset = 0;
    clearSelectedSession();
    syncWorkspaceWriteGuards();
    void loadSessions();
    void loadDocuments();
    void loadAdminOverview();
  });

  els.newSession.addEventListener("click", () => {
    void createSession("New RAG conversation");
  });

  els.reloadSessions.addEventListener("click", () => {
    void loadSessions();
  });

  els.chatForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void submitQuestion();
  });

  els.reloadDocuments.addEventListener("click", () => {
    void loadDocuments();
  });

  els.documentFile.addEventListener("change", () => {
    void loadMarkdownFile();
  });

  els.documentForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void uploadDocument();
  });

  els.reindexDryRun.addEventListener("click", () => {
    void reindexDocuments(true);
  });

  els.reindexWrite.addEventListener("click", () => {
    void reindexDocuments(false);
  });

  els.reloadAdmin.addEventListener("click", () => {
    void loadAdminOverview();
  });

  els.adminWorkspaceForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void createWorkspaceFromAdmin();
  });

  els.adminWorkspaceEditForm.addEventListener("submit", (event) => {
    event.preventDefault();
    void updateWorkspaceFromAdmin();
  });

  els.archiveAdminWorkspace.addEventListener("click", () => {
    void archiveWorkspaceFromAdmin();
  });

  els.restoreAdminWorkspace.addEventListener("click", () => {
    void restoreWorkspaceFromAdmin();
  });

  els.adminWorkspaceFilterAll.addEventListener("click", () => {
    setAdminWorkspaceFilter("all");
  });

  els.adminWorkspaceFilterActive.addEventListener("click", () => {
    setAdminWorkspaceFilter("active");
  });

  els.adminWorkspaceFilterArchived.addEventListener("click", () => {
    setAdminWorkspaceFilter("archived");
  });

  els.adminPrevWorkspaces.addEventListener("click", () => {
    state.admin.workspaceOffset = Math.max(
      0,
      state.admin.workspaceOffset - state.admin.workspaceLimit,
    );
    clearAdminWorkspaceSelectionState();
    void loadAdminOverview();
  });

  els.adminNextWorkspaces.addEventListener("click", () => {
    state.admin.workspaceOffset += state.admin.workspaceLimit;
    clearAdminWorkspaceSelectionState();
    void loadAdminOverview();
  });

  els.adminWorkspaceSearchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    state.admin.workspaceSearch = els.adminWorkspaceSearch.value.trim();
    state.admin.workspaceOffset = 0;
    clearAdminWorkspaceSelectionState();
    void loadAdminOverview();
  });

  els.adminClearWorkspaceSearch.addEventListener("click", () => {
    clearAdminWorkspaceSearch();
    void loadAdminOverview();
  });

  els.adminBulkArchiveWorkspaces.addEventListener("click", () => {
    void bulkArchiveWorkspacesFromAdmin();
  });

  els.adminBulkRestoreWorkspaces.addEventListener("click", () => {
    void bulkRestoreWorkspacesFromAdmin();
  });

  els.adminClearWorkspaceSelection.addEventListener("click", () => {
    clearAdminWorkspaceSelection();
  });

  els.adminFilterForm.addEventListener("submit", (event) => {
    event.preventDefault();
    readAdminFilters();
    state.admin.logOffset = 0;
    void loadAdminOverview();
  });

  els.clearAdminFilters.addEventListener("click", () => {
    clearAdminFilters();
    void loadAdminOverview();
  });

  els.exportAdminJsonl.addEventListener("click", () => {
    void exportAdminLogs("jsonl");
  });

  els.exportAdminCsv.addEventListener("click", () => {
    void exportAdminLogs("csv");
  });

  els.adminPrevLogs.addEventListener("click", () => {
    state.admin.logOffset = Math.max(0, state.admin.logOffset - state.admin.logLimit);
    void loadAdminOverview();
  });

  els.adminNextLogs.addEventListener("click", () => {
    state.admin.logOffset += state.admin.logLimit;
    void loadAdminOverview();
  });
}

function authHeaders() {
  return {
    Authorization: `Bearer ${state.apiKey || "dev-key"}`,
    "Content-Type": "application/json",
    "X-Workspace-ID": state.workspaceId || "public",
  };
}

async function apiFetch(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      ...authHeaders(),
      ...(options.headers || {}),
    },
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    let body = null;
    try {
      body = await response.json();
      detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      detail = await response.text();
    }
    throw buildHttpError(response, body, detail);
  }

  return response;
}

async function loadSessions() {
  setStatus("Loading sessions");
  try {
    const response = await apiFetch("/chat/sessions?limit=50&offset=0");
    const body = await response.json();
    state.sessions = body.sessions || [];
    renderSessions();

    if (state.sessionId) {
      const selected = state.sessions.find((item) => item.id === state.sessionId);
      if (selected) {
        selectSession(selected.id, selected.title || "Untitled session");
      }
    }

    setStatus("Ready");
  } catch (error) {
    setError(error.message);
  }
}

async function loadDocuments() {
  setDocumentStatus("Loading documents");
  try {
    const response = await apiFetch("/documents?limit=50&offset=0");
    const body = await response.json();
    state.documents = body.documents || [];
    renderDocuments();
    setDocumentStatus(`Loaded ${state.documents.length} document(s)`);
  } catch (error) {
    setDocumentError(error.message);
  }
}

async function loadAdminOverview() {
  setAdminStatus("Loading admin overview");
  try {
    const [workspaceResponse, logResponse] = await Promise.all([
      apiFetch(buildWorkspacesUrl()),
      apiFetch(buildChatLogsUrl()),
    ]);
    const [workspaceBody, logBody] = await Promise.all([
      workspaceResponse.json(),
      logResponse.json(),
    ]);

    state.admin.workspaces = workspaceBody.workspaces || [];
    pruneAdminWorkspaceSelection();
    state.admin.logs = logBody.logs || [];
    renderAdminOverview({
      workspaceTotal: workspaceBody.total ?? state.admin.workspaces.length,
      workspaceCount: workspaceBody.count ?? state.admin.workspaces.length,
      workspaceLimit: workspaceBody.limit ?? state.admin.workspaceLimit,
      workspaceOffset: workspaceBody.offset ?? state.admin.workspaceOffset,
      logTotal: logBody.count ?? state.admin.logs.length,
      logLimit: logBody.limit ?? state.admin.logLimit,
      logOffset: logBody.offset ?? state.admin.logOffset,
    });
    setAdminStatus(`Updated ${formatTimestamp(new Date().toISOString())}`);
  } catch (error) {
    setAdminError(error.message);
  }
}

async function createWorkspaceFromAdmin() {
  const workspaceId = els.adminWorkspaceId.value.trim();
  if (!workspaceId) {
    setAdminError("workspace id is required");
    return;
  }

  els.createAdminWorkspace.disabled = true;
  setAdminStatus("Creating workspace");
  try {
    const response = await apiFetch("/workspaces", {
      method: "POST",
      body: JSON.stringify({
        id: workspaceId,
        name: optionalText(els.adminWorkspaceName.value),
        description: optionalText(els.adminWorkspaceDescription.value),
        metadata: {
          created_by: "web_ui",
        },
      }),
    });
    const body = await response.json();
    const workspace = body.workspace;
    const changed = workspace.id !== state.workspaceId;
    state.workspaceId = workspace.id;
    els.workspaceId.value = state.workspaceId;
    localStorage.setItem("rag.workspaceId", state.workspaceId);
    state.admin.workspaceOffset = 0;
    state.admin.workspaceFilter = "all";
    clearAdminWorkspaceSearch();
    state.admin.logOffset = 0;
    if (changed) {
      clearSelectedSession();
    }
    els.adminWorkspaceForm.reset();
    await Promise.all([loadSessions(), loadDocuments(), loadAdminOverview()]);
    setAdminStatus(
      body.created
        ? `Created workspace ${workspace.id}`
        : `Workspace ready ${workspace.id}`,
    );
  } catch (error) {
    setAdminError(error.message);
  } finally {
    els.createAdminWorkspace.disabled = false;
  }
}

async function updateWorkspaceFromAdmin() {
  const workspaceId = els.adminEditWorkspaceId.value.trim() || state.workspaceId;
  if (!workspaceId) {
    setAdminError("workspace id is required");
    return;
  }

  let metadata = {};
  try {
    metadata = parseMetadataJson(els.adminEditWorkspaceMetadata.value);
  } catch (error) {
    setAdminError(error.message);
    return;
  }

  els.saveAdminWorkspace.disabled = true;
  setAdminStatus("Saving workspace");
  try {
    const response = await apiFetch(`/workspaces/${encodeURIComponent(workspaceId)}`, {
      method: "PATCH",
      body: JSON.stringify({
        name: optionalText(els.adminEditWorkspaceName.value),
        description: optionalText(els.adminEditWorkspaceDescription.value),
        metadata,
      }),
    });
    const body = await response.json();
    replaceAdminWorkspace(body.workspace);
    await loadAdminOverview();
    setAdminStatus(`Updated workspace ${body.workspace.id}`);
  } catch (error) {
    setAdminError(error.message);
  } finally {
    els.saveAdminWorkspace.disabled = false;
  }
}

async function archiveWorkspaceFromAdmin() {
  const workspaceId = els.adminEditWorkspaceId.value.trim() || state.workspaceId;
  if (!workspaceId) {
    setAdminError("workspace id is required");
    return;
  }

  setWorkspaceLifecycleButtonsDisabled(true);
  setAdminStatus("Archiving workspace");
  try {
    const response = await apiFetch(
      `/workspaces/${encodeURIComponent(workspaceId)}/archive`,
      {
        method: "POST",
        body: JSON.stringify({
          reason: optionalText(els.adminArchiveWorkspaceReason.value),
        }),
      },
    );
    const body = await response.json();
    replaceAdminWorkspace(body.workspace);
    if (body.workspace.id === state.workspaceId) {
      state.admin.workspaceFilter = "all";
      state.admin.workspaceOffset = 0;
      renderAdminWorkspaceFilters();
    }
    await loadAdminOverview();
    setAdminStatus(`Archived workspace ${body.workspace.id}`);
  } catch (error) {
    setAdminError(error.message);
  } finally {
    setWorkspaceLifecycleButtonsDisabled(false);
  }
}

async function restoreWorkspaceFromAdmin() {
  const workspaceId = els.adminEditWorkspaceId.value.trim() || state.workspaceId;
  if (!workspaceId) {
    setAdminError("workspace id is required");
    return;
  }

  setWorkspaceLifecycleButtonsDisabled(true);
  setAdminStatus("Restoring workspace");
  try {
    const response = await apiFetch(
      `/workspaces/${encodeURIComponent(workspaceId)}/restore`,
      {
        method: "POST",
      },
    );
    const body = await response.json();
    replaceAdminWorkspace(body.workspace);
    await loadAdminOverview();
    setAdminStatus(`Restored workspace ${body.workspace.id}`);
  } catch (error) {
    setAdminError(error.message);
  } finally {
    setWorkspaceLifecycleButtonsDisabled(false);
  }
}

async function bulkArchiveWorkspacesFromAdmin() {
  const workspaceIds = selectedAdminWorkspaceIds();
  if (!workspaceIds.length) {
    setAdminError("select at least one workspace");
    return;
  }

  setAdminWorkspaceBulkButtonsDisabled(true);
  setAdminStatus("Archiving selected workspaces");
  try {
    const response = await apiFetch("/workspaces/bulk/archive", {
      method: "POST",
      body: JSON.stringify({
        ids: workspaceIds,
        reason: optionalText(els.adminArchiveWorkspaceReason.value),
      }),
    });
    const body = await response.json();
    if (workspaceIds.includes(state.workspaceId)) {
      state.admin.workspaceFilter = "all";
      state.admin.workspaceOffset = 0;
      renderAdminWorkspaceFilters();
    }
    clearAdminWorkspaceSelectionState();
    await loadAdminOverview();
    setAdminStatus(`Archived ${body.updated_count} workspace(s)`);
  } catch (error) {
    setAdminError(error.message);
  } finally {
    syncAdminWorkspaceSelection();
  }
}

async function bulkRestoreWorkspacesFromAdmin() {
  const workspaceIds = selectedAdminWorkspaceIds();
  if (!workspaceIds.length) {
    setAdminError("select at least one workspace");
    return;
  }

  setAdminWorkspaceBulkButtonsDisabled(true);
  setAdminStatus("Restoring selected workspaces");
  try {
    const response = await apiFetch("/workspaces/bulk/restore", {
      method: "POST",
      body: JSON.stringify({
        ids: workspaceIds,
      }),
    });
    const body = await response.json();
    clearAdminWorkspaceSelectionState();
    await loadAdminOverview();
    setAdminStatus(`Restored ${body.updated_count} workspace(s)`);
  } catch (error) {
    setAdminError(error.message);
  } finally {
    syncAdminWorkspaceSelection();
  }
}

function replaceAdminWorkspace(workspace) {
  state.admin.workspaces = [
    workspace,
    ...state.admin.workspaces.filter((item) => item.id !== workspace.id),
  ];
}

function buildChatLogsUrl() {
  const params = buildChatLogParams({
    limit: state.admin.logLimit,
    offset: state.admin.logOffset,
  });
  return `/chat/logs?${params.toString()}`;
}

function buildWorkspacesUrl() {
  const params = new URLSearchParams({
    limit: String(state.admin.workspaceLimit),
    offset: String(state.admin.workspaceOffset),
    status: state.admin.workspaceFilter,
  });
  if (state.admin.workspaceSearch) {
    params.set("q", state.admin.workspaceSearch);
  }
  return `/workspaces?${params.toString()}`;
}

function buildChatLogsExportUrl(format) {
  const params = buildChatLogParams({
    limit: 1000,
    offset: 0,
  });
  params.set("format", format);
  return `/chat/logs/export?${params.toString()}`;
}

function buildChatLogParams({ limit, offset }) {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  if (state.admin.filters.requestId) {
    params.set("request_id", state.admin.filters.requestId);
  }
  if (state.admin.filters.sessionId) {
    params.set("session_id", state.admin.filters.sessionId);
  }
  if (state.admin.filters.citationValid) {
    params.set("citation_valid", state.admin.filters.citationValid);
  }
  if (state.admin.filters.refusalOnly) {
    params.set("refusal_only", "true");
  }
  return params;
}

function readAdminFilters() {
  state.admin.filters = {
    requestId: els.adminRequestId.value.trim(),
    sessionId: els.adminSessionId.value.trim(),
    citationValid: els.adminCitationValid.value,
    refusalOnly: els.adminRefusalOnly.checked,
  };
}

function clearAdminFilters() {
  state.admin.filters = {
    requestId: "",
    sessionId: "",
    citationValid: "",
    refusalOnly: false,
  };
  state.admin.logOffset = 0;
  els.adminRequestId.value = "";
  els.adminSessionId.value = "";
  els.adminCitationValid.value = "";
  els.adminRefusalOnly.checked = false;
}

function clearAdminWorkspaceSearch() {
  state.admin.workspaceSearch = "";
  els.adminWorkspaceSearch.value = "";
  state.admin.workspaceOffset = 0;
  clearAdminWorkspaceSelectionState();
}

function selectedAdminWorkspaceIds() {
  return Array.from(state.admin.selectedWorkspaceIds);
}

function pruneAdminWorkspaceSelection() {
  const visibleWorkspaceIds = new Set(
    state.admin.workspaces.map((workspace) => workspace.id),
  );
  for (const workspaceId of selectedAdminWorkspaceIds()) {
    if (!visibleWorkspaceIds.has(workspaceId)) {
      state.admin.selectedWorkspaceIds.delete(workspaceId);
    }
  }
}

function clearAdminWorkspaceSelection() {
  clearAdminWorkspaceSelectionState();
  renderAdminWorkspaces();
}

function clearAdminWorkspaceSelectionState() {
  state.admin.selectedWorkspaceIds.clear();
}

function toggleAdminWorkspaceSelection(workspaceId, selected) {
  if (selected) {
    state.admin.selectedWorkspaceIds.add(workspaceId);
  } else {
    state.admin.selectedWorkspaceIds.delete(workspaceId);
  }
  syncAdminWorkspaceSelection();
}

function syncAdminWorkspaceSelection() {
  const selectedCount = state.admin.selectedWorkspaceIds.size;
  els.adminWorkspaceSelectionSummary.textContent = `${selectedCount} selected`;
  setAdminWorkspaceBulkButtonsDisabled(selectedCount === 0);
}

function setAdminWorkspaceBulkButtonsDisabled(disabled) {
  els.adminBulkArchiveWorkspaces.disabled = disabled;
  els.adminBulkRestoreWorkspaces.disabled = disabled;
  els.adminClearWorkspaceSelection.disabled = disabled;
}

function syncWorkspaceEditForm() {
  const workspace = currentAdminWorkspace();
  els.adminEditWorkspaceId.value = state.workspaceId || "public";
  els.adminEditWorkspaceName.value = workspace?.name || "";
  els.adminEditWorkspaceDescription.value = workspace?.description || "";
  els.adminEditWorkspaceMetadata.value = formatMetadataJson(workspace?.metadata || {});
  els.adminArchiveWorkspaceReason.value = workspace?.archived_reason || "";
  syncWorkspaceLifecycleButtons(workspace);
  syncWorkspaceWriteGuards();
}

function currentAdminWorkspace() {
  return (
    state.admin.workspaces.find((item) => item.id === state.workspaceId) || null
  );
}

function isCurrentWorkspaceArchived() {
  return Boolean(currentAdminWorkspace()?.archived_at);
}

function syncWorkspaceWriteGuards() {
  const isArchived = isCurrentWorkspaceArchived();
  const message = isArchived
    ? "Workspace archived: read-only mode. Restore it in Admin before chat, upload, reindex, or session creation."
    : "";

  els.workspaceArchiveBanner.hidden = !isArchived;
  els.workspaceArchiveBanner.textContent = message;
  els.newSession.disabled = isArchived;
  els.question.disabled = isArchived;
  if (!state.sending) {
    els.send.disabled = isArchived;
  }

  for (const element of [
    els.documentSourceUri,
    els.documentTitle,
    els.documentFile,
    els.documentMarkdown,
    els.uploadDocument,
    els.reindexSourceUri,
    els.reindexDryRun,
    els.reindexWrite,
  ]) {
    element.disabled = isArchived;
  }
}

function guardArchivedWorkspace(statusWriter) {
  if (!isCurrentWorkspaceArchived()) {
    return false;
  }
  statusWriter("Workspace archived: restore it before writing changes.");
  syncWorkspaceWriteGuards();
  return true;
}

function syncWorkspaceLifecycleButtons(workspace) {
  const isArchived = Boolean(workspace?.archived_at);
  els.archiveAdminWorkspace.disabled = isArchived;
  els.restoreAdminWorkspace.disabled = !isArchived;
}

function setWorkspaceLifecycleButtonsDisabled(disabled) {
  if (disabled) {
    els.archiveAdminWorkspace.disabled = true;
    els.restoreAdminWorkspace.disabled = true;
    return;
  }
  syncWorkspaceLifecycleButtons(currentAdminWorkspace());
}

function optionalText(value) {
  const text = String(value || "").trim();
  return text || null;
}

function parseMetadataJson(value) {
  const text = String(value || "").trim();
  if (!text) {
    return {};
  }
  const parsed = JSON.parse(text);
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw createAppError("metadata must be a JSON object");
  }
  return parsed;
}

function formatMetadataJson(value) {
  return JSON.stringify(value || {}, null, 2);
}

async function exportAdminLogs(format) {
  readAdminFilters();
  const extension = format === "csv" ? "csv" : "jsonl";
  setAdminStatus(`Exporting ${extension.toUpperCase()}`);
  try {
    const response = await apiFetch(buildChatLogsExportUrl(extension));
    const blob = await response.blob();
    downloadBlob(
      blob,
      `rag-chat-logs-${formatFilenamePart(state.workspaceId)}-${formatTimestampForFilename(
        new Date(),
      )}.${extension}`,
    );
    setAdminStatus(`Exported ${extension.toUpperCase()}`);
  } catch (error) {
    setAdminError(error.message);
  }
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.append(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

async function loadMarkdownFile() {
  const file = els.documentFile.files[0];
  if (!file) {
    return;
  }
  if (guardArchivedWorkspace(setDocumentError)) {
    els.documentFile.value = "";
    return;
  }

  const text = await file.text();
  els.documentMarkdown.value = text;
  if (!els.documentSourceUri.value.trim()) {
    els.documentSourceUri.value = `uploads/${file.name}`;
  }
  if (!els.documentTitle.value.trim()) {
    els.documentTitle.value = file.name.replace(/\.(md|markdown|txt)$/i, "");
  }
}

async function uploadDocument() {
  if (guardArchivedWorkspace(setDocumentError)) {
    return;
  }
  const sourceUri = els.documentSourceUri.value.trim();
  const markdown = els.documentMarkdown.value.trim();
  const title = els.documentTitle.value.trim();
  if (!sourceUri || !markdown) {
    setDocumentError("source_uri and markdown are required");
    return;
  }

  els.uploadDocument.disabled = true;
  setDocumentStatus("Uploading document");
  try {
    const response = await apiFetch("/documents", {
      method: "POST",
      body: JSON.stringify({
        source_uri: sourceUri,
        markdown,
        title: title || null,
        metadata: {
          uploaded_by: "web_ui",
        },
      }),
    });
    const body = await response.json();
    const action = body.inserted ? "inserted" : "skipped";
    setDocumentStatus(
      `Document ${action}: ${body.chunks_inserted} chunk(s), ${body.reason || "ok"}`,
    );
    els.documentMarkdown.value = "";
    els.documentFile.value = "";
    await loadDocuments();
  } catch (error) {
    setDocumentError(error.message);
  } finally {
    syncWorkspaceWriteGuards();
  }
}

async function reindexDocuments(dryRun) {
  if (guardArchivedWorkspace(setDocumentError)) {
    return;
  }
  const sourceUri = els.reindexSourceUri.value.trim();
  els.reindexDryRun.disabled = true;
  els.reindexWrite.disabled = true;
  setDocumentStatus(dryRun ? "Checking reindex impact" : "Reindexing documents");

  try {
    const response = await apiFetch("/documents/reindex", {
      method: "POST",
      body: JSON.stringify({
        source_uri: sourceUri || null,
        dry_run: dryRun,
        batch_size: 32,
      }),
    });
    const body = await response.json();
    setDocumentStatus(
      [
        dryRun ? "Dry run complete" : "Reindex complete",
        `${body.chunks_matched} matched`,
        `${body.chunks_updated} updated`,
        body.model,
      ].join(" / "),
    );
    await loadDocuments();
  } catch (error) {
    setDocumentError(error.message);
  } finally {
    syncWorkspaceWriteGuards();
  }
}

function renderDocuments() {
  els.documentList.innerHTML = "";
  if (!state.documents.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No documents indexed yet";
    els.documentList.append(empty);
    return;
  }

  for (const documentItem of state.documents) {
    const item = document.createElement("article");
    item.className = "document-item";

    const title = document.createElement("div");
    title.className = "document-title";
    title.textContent = documentItem.title || "Untitled document";

    const uri = document.createElement("div");
    uri.className = "document-uri";
    uri.textContent = documentItem.source_uri;

    const meta = document.createElement("div");
    meta.className = "document-meta";
    meta.textContent = `${documentItem.chunk_count} chunk(s) / ${documentItem.visibility}`;

    item.append(title, uri, meta);
    els.documentList.append(item);
  }
}

function renderAdminOverview({
  workspaceTotal,
  workspaceCount,
  workspaceLimit,
  workspaceOffset,
  logTotal,
  logLimit,
  logOffset,
}) {
  els.adminWorkspaceCount.textContent = String(workspaceTotal);
  els.adminLogCount.textContent = String(logTotal);
  renderAdminWorkspaceFilters();
  renderAdminWorkspaces();
  renderAdminWorkspacePagination({
    count: workspaceCount,
    total: workspaceTotal,
    limit: workspaceLimit,
    offset: workspaceOffset,
  });
  syncWorkspaceEditForm();
  syncWorkspaceWriteGuards();
  renderAdminLogs();
  renderAdminPagination({
    count: logTotal,
    limit: logLimit,
    offset: logOffset,
  });
}

function renderAdminPagination({ count, limit, offset }) {
  const start = count > 0 ? offset + 1 : 0;
  const end = count > 0 ? offset + count : 0;
  els.adminPageInfo.textContent = count > 0 ? `Logs ${start}-${end}` : "No logs";
  els.adminPrevLogs.disabled = offset <= 0;
  els.adminNextLogs.disabled = count < limit;
}

function renderAdminWorkspacePagination({ count, total, limit, offset }) {
  const start = total > 0 ? offset + 1 : 0;
  const end = total > 0 ? offset + count : 0;
  const emptyLabel = workspaceFilterEmptyMessage();
  els.adminWorkspacePageInfo.textContent =
    total > 0 ? `Workspaces ${start}-${end} of ${total}` : emptyLabel;
  els.adminPrevWorkspaces.disabled = offset <= 0;
  els.adminNextWorkspaces.disabled = offset + count >= total || count < limit;
}

function setAdminWorkspaceFilter(filter) {
  state.admin.workspaceFilter = filter;
  state.admin.workspaceOffset = 0;
  clearAdminWorkspaceSelectionState();
  renderAdminWorkspaceFilters();
  void loadAdminOverview();
}

function renderAdminWorkspaceFilters() {
  const filterButtons = {
    all: els.adminWorkspaceFilterAll,
    active: els.adminWorkspaceFilterActive,
    archived: els.adminWorkspaceFilterArchived,
  };
  for (const [filter, button] of Object.entries(filterButtons)) {
    button.setAttribute(
      "aria-pressed",
      String(state.admin.workspaceFilter === filter),
    );
  }
}

function filteredAdminWorkspaces() {
  return state.admin.workspaces.filter((workspace) => {
    const isArchived = Boolean(workspace.archived_at);
    if (state.admin.workspaceFilter === "active") {
      return !isArchived;
    }
    if (state.admin.workspaceFilter === "archived") {
      return isArchived;
    }
    return true;
  });
}

function workspaceFilterEmptyMessage() {
  if (state.admin.workspaceSearch && !state.admin.workspaces.length) {
    return "No matching workspaces";
  }
  if (state.admin.workspaceFilter === "active") {
    return "No active workspaces";
  }
  if (state.admin.workspaceFilter === "archived") {
    return "No archived workspaces";
  }
  return "No accessible workspaces";
}

function renderAdminWorkspaces() {
  els.adminWorkspaceList.innerHTML = "";
  const workspaces = filteredAdminWorkspaces();
  const searchSuffix = state.admin.workspaceSearch ? " matching search" : "";
  els.adminWorkspaceFilterSummary.textContent = `Showing ${workspaces.length} of ${state.admin.workspaces.length} on this page${searchSuffix}`;
  if (!workspaces.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = workspaceFilterEmptyMessage();
    els.adminWorkspaceList.append(empty);
    syncAdminWorkspaceSelection();
    return;
  }

  for (const workspace of workspaces) {
    const isArchived = Boolean(workspace.archived_at);
    const item = document.createElement("article");
    item.className = `admin-item admin-workspace${
      workspace.id === state.workspaceId ? " active" : ""
    }${isArchived ? " archived" : ""}${
      state.admin.selectedWorkspaceIds.has(workspace.id) ? " selected" : ""
    }`;

    const header = document.createElement("div");
    header.className = "admin-item-header admin-workspace-header";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.className = "admin-workspace-checkbox";
    checkbox.checked = state.admin.selectedWorkspaceIds.has(workspace.id);
    checkbox.setAttribute("aria-label", `Select workspace ${workspace.id}`);
    checkbox.addEventListener("change", () => {
      toggleAdminWorkspaceSelection(workspace.id, checkbox.checked);
      item.classList.toggle("selected", checkbox.checked);
    });

    const title = document.createElement("button");
    title.type = "button";
    title.className = "admin-title admin-workspace-title-button";
    title.textContent = workspace.name || workspace.id;
    title.addEventListener("click", () => {
      selectWorkspace(workspace.id);
    });

    const id = document.createElement("span");
    id.className = "admin-badge";
    id.textContent = workspace.id;

    const description = document.createElement("div");
    description.className = "admin-text";
    description.textContent = workspace.description || "No description";

    const meta = document.createElement("div");
    meta.className = "admin-meta";
    meta.textContent = workspaceLifecycleText(workspace);

    header.append(checkbox, title, id);
    item.append(header, description, meta);
    els.adminWorkspaceList.append(item);
  }
  syncAdminWorkspaceSelection();
}

function workspaceLifecycleText(workspace) {
  if (workspace.archived_at) {
    const reason = workspace.archived_reason
      ? ` / ${workspace.archived_reason}`
      : "";
    return `Archived ${formatTimestamp(workspace.archived_at)}${reason}`;
  }
  return `Updated ${formatTimestamp(workspace.updated_at)}`;
}

function renderAdminLogs() {
  els.adminLogList.innerHTML = "";
  if (!state.admin.logs.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No chat logs for this workspace";
    els.adminLogList.append(empty);
    return;
  }

  for (const log of state.admin.logs) {
    const item = document.createElement("article");
    item.className = "admin-item";

    const header = document.createElement("div");
    header.className = "admin-item-header";

    const question = document.createElement("span");
    question.className = "admin-title";
    question.textContent = truncateText(log.question, 72);

    const verdict = document.createElement("span");
    verdict.className = "admin-badge";
    verdict.textContent = chatLogVerdict(log);

    const answer = document.createElement("div");
    answer.className = "admin-text";
    answer.textContent = truncateText(log.answer, 130);

    const meta = document.createElement("div");
    meta.className = "admin-meta";
    meta.textContent = [
      `${log.latency_ms} ms`,
      formatTimestamp(log.created_at),
      `request ${log.request_id}`,
    ].join(" / ");

    const detail = buildChatLogAuditDetails(log);

    header.append(question, verdict);
    item.append(header, answer, meta, detail);
    els.adminLogList.append(item);
  }
}

function buildChatLogAuditDetails(log) {
  const detail = document.createElement("details");
  detail.className = "admin-detail";

  const summary = document.createElement("summary");
  summary.textContent = "Audit details";

  const grid = document.createElement("div");
  grid.className = "admin-detail-grid";

  appendAdminDetailRow(grid, "Workspace", log.workspace_id || state.workspaceId);
  appendAdminDetailRow(grid, "Session", log.session_id || "none");
  appendAdminDetailRow(grid, "Request", log.request_id || "unknown");
  appendAdminDetailRow(grid, "Citation", formatCitationStatus(log.citation_valid));
  appendAdminDetailRow(grid, "Sources", `${(log.sources || []).length} source(s)`);
  appendAdminDetailRow(grid, "Refusal", formatRefusal(log.refusal));
  appendAdminDetailRow(grid, "Retrieval", formatRetrieval(log.retrieval));
  appendAdminDetailRow(grid, "Query rewrite", formatQueryRewrite(log.retrieval?.query_rewrite));
  appendAdminDetailRow(
    grid,
    "Metadata filter",
    formatJsonPreview(log.retrieval?.metadata_filter),
  );
  appendAdminDetailRow(grid, "Usage", formatUsage(log.usage));
  appendAdminDetailRow(grid, "Cost", formatCost(log.usage));

  detail.append(summary, grid);
  return detail;
}

function appendAdminDetailRow(grid, label, value) {
  const row = document.createElement("div");
  row.className = "admin-detail-row";

  const labelEl = document.createElement("div");
  labelEl.className = "admin-detail-label";
  labelEl.textContent = label;

  const valueEl = document.createElement("div");
  valueEl.className = "admin-detail-value";
  valueEl.textContent = value || "unknown";

  row.append(labelEl, valueEl);
  grid.append(row);
}

function selectWorkspace(workspaceId) {
  const nextWorkspaceId = workspaceId || "public";
  const changed = nextWorkspaceId !== state.workspaceId;
  state.workspaceId = nextWorkspaceId;
  els.workspaceId.value = state.workspaceId;
  localStorage.setItem("rag.workspaceId", state.workspaceId);
  state.admin.logOffset = 0;
  if (changed) {
    clearSelectedSession();
  }
  syncWorkspaceEditForm();
  void loadSessions();
  void loadDocuments();
  void loadAdminOverview();
}

async function createSession(title) {
  if (guardArchivedWorkspace(setError)) {
    return null;
  }
  setStatus("Creating session");
  try {
    const response = await apiFetch("/chat/sessions", {
      method: "POST",
      body: JSON.stringify({
        title,
        metadata: {
          created_by: "web_ui",
        },
      }),
    });
    const body = await response.json();
    const session = body.session;
    state.sessionId = session.id;
    localStorage.setItem("rag.sessionId", state.sessionId);
    state.sessions = [session, ...state.sessions.filter((item) => item.id !== session.id)];
    renderSessions();
    selectSession(session.id, session.title || "Untitled session");
    setStatus("Session ready");
    return session;
  } catch (error) {
    setError(error.message);
    return null;
  }
}

function renderSessions() {
  els.sessionList.innerHTML = "";
  if (!state.sessions.length) {
    const empty = document.createElement("div");
    empty.className = "empty";
    empty.textContent = "No sessions yet";
    els.sessionList.append(empty);
    return;
  }

  for (const session of state.sessions) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `session-item${session.id === state.sessionId ? " active" : ""}`;
    button.addEventListener("click", () => {
      selectSession(session.id, session.title || "Untitled session");
    });

    const title = document.createElement("span");
    title.className = "session-title";
    title.textContent = session.title || "Untitled session";

    const id = document.createElement("span");
    id.className = "session-id";
    id.textContent = session.id;

    button.append(title, id);
    els.sessionList.append(button);
  }
}

function selectSession(sessionId, title) {
  state.sessionId = sessionId;
  localStorage.setItem("rag.sessionId", sessionId);
  els.sessionTitle.textContent = title;
  renderSessions();
  void loadHistory(sessionId);
}

async function loadHistory(sessionId) {
  setStatus("Loading history");
  try {
    const response = await apiFetch(
      `/chat/sessions/${encodeURIComponent(sessionId)}/logs?limit=50&offset=0`,
    );
    const body = await response.json();
    els.messages.innerHTML = "";
    for (const log of body.logs || []) {
      appendMessage("user", log.question);
      appendMessage("assistant", log.answer, log.sources || []);
    }
    if (!(body.logs || []).length) {
      renderEmptyMessages();
    }
    setStatus("Ready");
  } catch (error) {
    setError(error.message);
  }
}

async function submitQuestion(retryQuestion = "") {
  const question = (retryQuestion || els.question.value).trim();
  if (!question || state.sending) {
    return;
  }
  if (guardArchivedWorkspace(setError)) {
    return;
  }

  state.sending = true;
  els.send.disabled = true;
  if (!retryQuestion) {
    els.question.value = "";
  }
  appendMessage("user", question);
  const assistantMessage = appendMessage("assistant", "");

  try {
    if (!state.sessionId) {
      const title = question.length > 80 ? `${question.slice(0, 77)}...` : question;
      const session = await createSession(title);
      if (!session) {
        throw createAppError("Could not create chat session", {
          retryable: true,
        });
      }
    }

    await streamAnswer(question, assistantMessage);
    setStatus("Ready");
  } catch (error) {
    const appError = normalizeError(error);
    setError(formatStatusError(appError));
    renderMessageError(assistantMessage, appError, question);
  } finally {
    state.sending = false;
    syncWorkspaceWriteGuards();
    if (!isCurrentWorkspaceArchived()) {
      els.question.focus();
    }
  }
}

async function streamAnswer(question, assistantMessage) {
  setStatus("Streaming answer");
  const response = await apiFetch("/chat/stream", {
    method: "POST",
    body: JSON.stringify({
      question,
      session_id: state.sessionId || null,
    }),
  });
  if (!response.body) {
    throw createAppError("The browser did not receive a streaming response.", {
      retryable: true,
    });
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() || "";

    for (const block of blocks) {
      const event = parseSseBlock(block);
      if (!event) {
        continue;
      }
      if (event.name === "answer_delta") {
        answer += event.data.delta || "";
        updateMessageContent(assistantMessage, answer);
      }
      if (event.name === "final") {
        renderSources(assistantMessage, event.data.sources || []);
      }
      if (event.name === "error") {
        throw buildStreamError(event.data);
      }
    }
  }
}

function parseSseBlock(block) {
  let name = "";
  const dataLines = [];

  for (const line of block.split("\n")) {
    if (line.startsWith("event:")) {
      name = line.replace("event:", "").trim();
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.replace("data:", "").trimStart());
    }
  }

  if (!name || !dataLines.length) {
    return null;
  }

  return {
    name,
    data: JSON.parse(dataLines.join("\n")),
  };
}

function appendMessage(role, text, sources = []) {
  clearEmptyMessages();
  const message = document.createElement("article");
  message.className = `message ${role}`;

  const roleEl = document.createElement("div");
  roleEl.className = "role";
  roleEl.textContent = role === "user" ? "You" : "Assistant";

  const content = document.createElement("div");
  content.className = "content";
  content.textContent = text;

  message.append(roleEl, content);
  els.messages.append(message);
  renderSources(message, sources);
  els.messages.scrollTop = els.messages.scrollHeight;
  return message;
}

function updateMessageContent(message, text) {
  message.querySelector(".content").textContent = text;
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderMessageError(message, error, question) {
  updateMessageContent(message, error.userMessage || error.message);
  const existing = message.querySelector(".message-error");
  if (existing) {
    existing.remove();
  }

  const wrapper = document.createElement("div");
  wrapper.className = "message-error";

  const title = document.createElement("div");
  title.className = "error-title";
  title.textContent = "Request failed";

  const detail = document.createElement("div");
  detail.className = "error-detail";
  detail.textContent = error.message || "The request could not be completed.";

  const metaItems = buildErrorMetaItems(error);
  wrapper.append(title, detail);
  if (metaItems.length) {
    const meta = document.createElement("div");
    meta.className = "error-meta";
    for (const item of metaItems) {
      const row = document.createElement("div");
      row.textContent = item;
      meta.append(row);
    }
    wrapper.append(meta);
  }

  if (question) {
    const actions = document.createElement("div");
    actions.className = "message-actions";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "retry-button";
    retry.textContent = "Retry";
    retry.addEventListener("click", () => {
      void submitQuestion(question);
    });
    actions.append(retry);
    wrapper.append(actions);
  }

  message.append(wrapper);
  els.messages.scrollTop = els.messages.scrollHeight;
}

function renderSources(message, sources) {
  const existing = message.querySelector(".sources");
  if (existing) {
    existing.remove();
  }
  if (!sources.length) {
    return;
  }

  const wrapper = document.createElement("div");
  wrapper.className = "sources";
  for (const source of sources) {
    const item = document.createElement("div");
    item.className = "source";

    const index = document.createElement("div");
    index.className = "source-index";
    index.textContent = `[${source.source_id}]`;

    const title = document.createElement("div");
    title.className = "source-title";
    title.textContent = source.section
      ? `${source.title} / ${source.section}`
      : source.title;

    item.append(index, title);
    wrapper.append(item);
  }
  message.append(wrapper);
}

function chatLogVerdict(log) {
  if (log.refusal) {
    return "refused";
  }
  if (log.citation_valid === false) {
    return "citation issue";
  }
  return "answered";
}

function formatCitationStatus(value) {
  if (value === true) {
    return "valid";
  }
  if (value === false) {
    return "invalid";
  }
  return "not checked";
}

function formatRefusal(refusal) {
  if (!refusal) {
    return "none";
  }
  const topScore = refusal.top_score === null ? "n/a" : formatNumber(refusal.top_score);
  return `${refusal.reason || "refused"} / top ${topScore} / threshold ${formatNumber(
    refusal.threshold,
  )}`;
}

function formatRetrieval(retrieval) {
  if (!retrieval) {
    return "none";
  }
  return [
    retrieval.mode || "unknown",
    `used ${formatInteger(retrieval.used_count)}`,
    `fused ${formatInteger(retrieval.fused_count)}`,
    `vector ${formatInteger(retrieval.vector_top_k)}`,
    `sparse ${formatInteger(retrieval.sparse_top_k)}`,
    `top ${formatNumber(retrieval.top_score)}`,
  ].join(" / ");
}

function formatQueryRewrite(queryRewrite) {
  if (!queryRewrite) {
    return "none";
  }
  const status = queryRewrite.rewritten ? "rewritten" : "unchanged";
  const provider = `${queryRewrite.provider || "none"}:${queryRewrite.model || "none"}`;
  const history = `history ${formatInteger(queryRewrite.history_turn_count)}`;
  const query = queryRewrite.retrieval_query
    ? ` / query ${truncateText(queryRewrite.retrieval_query, 80)}`
    : "";
  return `${status} / ${provider} / ${history}${query}`;
}

function formatUsage(usage) {
  if (!usage) {
    return "none";
  }
  return [
    `${usage.generator_provider || "unknown"}:${usage.model || "unknown"}`,
    `input ${formatInteger(usage.input_tokens)}`,
    `output ${formatInteger(usage.output_tokens)}`,
    `embedding ${formatInteger(usage.embedding_total_tokens)}`,
  ].join(" / ");
}

function formatCost(usage) {
  if (!usage) {
    return "none";
  }
  const estimated = usage.cost_estimated ? "estimated" : "not estimated";
  return `${formatCostAmount(usage.total_cost_usd)} ${usage.cost_currency || "USD"} / ${estimated}`;
}

function formatJsonPreview(value) {
  if (!value || (typeof value === "object" && !Object.keys(value).length)) {
    return "{}";
  }
  try {
    return truncateText(JSON.stringify(value), 140);
  } catch {
    return truncateText(String(value), 140);
  }
}

function formatInteger(value) {
  return Number.isFinite(Number(value)) ? String(Number(value)) : "0";
}

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "n/a";
  }
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "n/a";
  }
  return number.toFixed(4);
}

function formatCostAmount(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) {
    return "0.000000";
  }
  return number.toFixed(6);
}

function truncateText(value, maxLength) {
  const text = String(value || "").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, Math.max(0, maxLength - 3))}...`;
}

function formatTimestamp(value) {
  if (!value) {
    return "unknown";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatTimestampForFilename(date) {
  return date.toISOString().replace(/[:.]/g, "-");
}

function formatFilenamePart(value) {
  return String(value || "public").replace(/[^a-z0-9_-]+/gi, "-");
}

function buildHttpError(response, body, fallbackMessage) {
  const detail = body && typeof body === "object" ? body.detail : null;
  if (detail && typeof detail === "object") {
    return createAppError(detail.message || fallbackMessage, {
      status: response.status,
      provider: detail.provider,
      category: detail.category,
      retryable: detail.retryable,
      requestId: detail.request_id,
      userMessage: providerErrorUserMessage(detail.category),
    });
  }

  return createAppError(fallbackMessage, {
    status: response.status,
    retryable: response.status >= 500 || response.status === 429,
    userMessage: httpErrorUserMessage(response.status, fallbackMessage),
  });
}

function buildStreamError(data) {
  return createAppError(data.message || "The stream failed before completion.", {
    provider: data.provider,
    category: data.category,
    retryable: data.retryable,
    requestId: data.request_id,
    userMessage: providerErrorUserMessage(data.category),
  });
}

function createAppError(message, details = {}) {
  const error = new Error(message || "Request failed");
  error.isAppError = true;
  Object.assign(error, details);
  return error;
}

function normalizeError(error) {
  if (error && error.isAppError) {
    return error;
  }
  return createAppError(error?.message || "Request failed", {
    retryable: true,
  });
}

function providerErrorUserMessage(category) {
  const messages = {
    authentication: "The provider rejected authentication. Check the server OpenAI key.",
    permission: "The provider denied access for this model or workspace.",
    not_found: "The configured provider model or endpoint was not found.",
    invalid_request: "The provider rejected the request format or parameters.",
    rate_limit: "The provider rate limit was reached. Wait briefly, then retry.",
    timeout: "The provider timed out before completing the request.",
    network: "The provider network request failed. Check connectivity, then retry.",
    server_error: "The provider returned a server error. Retry after a short wait.",
    conflict: "The provider could not process the request right now.",
  };
  return messages[category] || "The request failed before the assistant could answer.";
}

function httpErrorUserMessage(status, fallbackMessage) {
  if (status === 401) {
    return "The API key was rejected. Update the API key and retry.";
  }
  if (status === 403) {
    return "This API key cannot access the selected workspace.";
  }
  if (status === 404) {
    return "The selected workspace or session was not found.";
  }
  if (status === 429) {
    return "Too many requests. Wait briefly, then retry.";
  }
  return fallbackMessage || "The request could not be completed.";
}

function buildErrorMetaItems(error) {
  const items = [];
  if (error.status) {
    items.push(`HTTP ${error.status}`);
  }
  if (error.category) {
    items.push(`Category: ${error.category}`);
  }
  if (typeof error.retryable === "boolean") {
    items.push(`Retryable: ${error.retryable ? "yes" : "no"}`);
  }
  if (error.requestId) {
    items.push(`Request: ${error.requestId}`);
  }
  return items;
}

function formatStatusError(error) {
  if (error.category) {
    return `Error: ${error.category}`;
  }
  if (error.status) {
    return `Error: HTTP ${error.status}`;
  }
  return "Request failed";
}

function renderEmptyMessages() {
  els.messages.innerHTML = "";
  const empty = document.createElement("div");
  empty.className = "empty";
  empty.textContent = "Create or select a session, then ask a question.";
  els.messages.append(empty);
}

function clearEmptyMessages() {
  for (const node of [...els.messages.querySelectorAll(".empty")]) {
    node.remove();
  }
}

function clearSelectedSession() {
  state.sessionId = "";
  localStorage.removeItem("rag.sessionId");
  els.sessionTitle.textContent = "No session selected";
  renderSessions();
  renderEmptyMessages();
}

function setStatus(message) {
  els.status.classList.remove("error");
  els.status.textContent = message;
}

function setError(message) {
  els.status.classList.add("error");
  els.status.textContent = message || "Request failed";
}

function setDocumentStatus(message) {
  els.documentStatus.classList.remove("error");
  els.documentStatus.textContent = message;
}

function setDocumentError(message) {
  els.documentStatus.classList.add("error");
  els.documentStatus.textContent = message || "Document request failed";
}

function setAdminStatus(message) {
  els.adminStatus.classList.remove("error");
  els.adminStatus.textContent = message;
}

function setAdminError(message) {
  els.adminStatus.classList.add("error");
  els.adminStatus.textContent = message || "Admin request failed";
}

init();
