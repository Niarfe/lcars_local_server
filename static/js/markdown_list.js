(function () {
  const filterInput = document.getElementById("markdown-filter");
  const rows = Array.from(document.querySelectorAll(".markdown-doc-row"));
  const archiveButton = document.getElementById("archive-markdown-context");
  const archiveModal = document.getElementById("archive-modal");
  const archiveSummary = document.getElementById("archive-summary");
  const archiveStatus = document.getElementById("archive-status");
  const archiveConfirm = document.getElementById("archive-confirm");
  const archiveCancel = document.getElementById("archive-cancel");
  const FILTER_KEY = "lcars-markdown-filter";
  let activeArchiveFolder = "";

  function getFolderContext(query) {
    const value = (query || "").trim();
    if (!value.endsWith("/")) return "";
    return value.split("/").filter(Boolean)[0] || "";
  }

  function updateNewDocumentLink(query) {
    const link = document.getElementById("new-markdown-context-link");
    if (!link) return;
    const folder = getFolderContext(query);
    link.href = folder ? `/md/new?folder=${encodeURIComponent(folder)}` : "/md/new";
    link.textContent = folder ? `NEW ${folder.toUpperCase()} DOC` : "NEW DOCUMENT";
  }

  function updateArchiveButton(query) {
    if (!archiveButton) return;
    const folder = getFolderContext(query);
    activeArchiveFolder = folder;
    archiveButton.classList.toggle("hidden", !folder);
    archiveButton.textContent = folder ? `ARCHIVE ${folder.toUpperCase()}` : "ARCHIVE";
  }

  function normalizeFolderFilter(value) {
    const folder = (value || "").trim().replace(/^\/+|\/+$/g, "");
    return folder ? `${folder.toLowerCase()}/` : "";
  }

  function getInitialFilter() {
    const params = new URLSearchParams(window.location.search);
    const folderFilter = normalizeFolderFilter(params.get("folder") || "");
    if (folderFilter) return folderFilter;
    return localStorage.getItem(FILTER_KEY) || "";
  }

  function applyFilter() {
    const query = (filterInput.value || "").trim().toLowerCase();
    localStorage.setItem(FILTER_KEY, query);
    updateNewDocumentLink(query);
    updateArchiveButton(query);

    rows.forEach((row) => {
      const name = row.dataset.name || "";
      const path = row.dataset.path || "";
      const visible =
        !query ||
        name.startsWith(query) ||
        path.startsWith(query) ||
        name.includes(query) ||
        path.includes(query);

      row.classList.toggle("hidden", !visible);
    });
  }

  function appendSummaryLine(label, value) {
    if (!archiveSummary) return;
    const row = document.createElement("div");
    row.className = "archive-summary-row";
    const labelEl = document.createElement("span");
    labelEl.className = "subtle";
    labelEl.textContent = label;
    const valueEl = document.createElement("span");
    valueEl.textContent = value;
    row.append(labelEl, valueEl);
    archiveSummary.append(row);
  }

  function renderArchivePreview(preview) {
    if (!archiveSummary) return;
    archiveSummary.replaceChildren();
    appendSummaryLine("ACTIVE", preview.active_path || "");
    appendSummaryLine("ARCHIVE", preview.archive_path || "");
    appendSummaryLine("ACTIVE FILES", String(preview.active_files ?? 0));
    appendSummaryLine(
      "ARCHIVE STATE",
      preview.archive_exists
        ? `EXISTS (${preview.archive_files ?? 0} FILES)`
        : "NEW FOLDER"
    );
    appendSummaryLine("OVERWRITES", String(preview.overwrite_files ?? 0));
  }

  function closeArchiveModal() {
    archiveModal?.classList.add("hidden");
    if (archiveStatus) archiveStatus.textContent = "";
  }

  async function openArchiveModal(folder) {
    if (!folder || !archiveModal || !archiveConfirm) return;
    archiveModal.classList.remove("hidden");
    archiveConfirm.disabled = true;
    archiveConfirm.textContent = "CONFIRM ARCHIVE";
    if (archiveSummary) archiveSummary.replaceChildren();
    if (archiveStatus) archiveStatus.textContent = "LOADING ARCHIVE PREFLIGHT";

    try {
      const response = await fetch(`/api/markdown/archive/preview/${encodeURIComponent(folder)}`);
      const data = await response.json();
      if (!data.ok) {
        if (archiveStatus) archiveStatus.textContent = data.error || "ARCHIVE PREFLIGHT FAILED";
        return;
      }
      renderArchivePreview(data.archive || {});
      archiveConfirm.disabled = false;
      if (archiveStatus) archiveStatus.textContent = "CONFIRM TO CREATE CHECKPOINT COMMITS AND ARCHIVE THIS FOLDER";
    } catch (error) {
      if (archiveStatus) archiveStatus.textContent = error.message || "ARCHIVE PREFLIGHT FAILED";
    }
  }

  async function archiveFolder(folder) {
    if (!folder || !archiveConfirm) return;
    archiveConfirm.disabled = true;
    archiveConfirm.textContent = "ARCHIVING";
    if (archiveStatus) archiveStatus.textContent = "ARCHIVE IN PROGRESS";

    try {
      const response = await fetch(`/api/markdown/archive/${encodeURIComponent(folder)}`, { method: "POST" });
      const data = await response.json();
      if (!data.ok) {
        if (archiveStatus) archiveStatus.textContent = data.error || "ARCHIVE FAILED";
        return;
      }
      const commits = (data.archive?.commits || []).map((commit) => commit.hash).filter(Boolean);
      if (archiveStatus) archiveStatus.textContent = commits.length ? `ARCHIVED: ${commits.join(", ")}` : "ARCHIVED";
      localStorage.removeItem(FILTER_KEY);
      window.location.href = "/markdown";
    } catch (error) {
      if (archiveStatus) archiveStatus.textContent = error.message || "ARCHIVE FAILED";
    } finally {
      archiveConfirm.disabled = false;
      archiveConfirm.textContent = "CONFIRM ARCHIVE";
    }
  }


  async function renameDoc(docId, docName, button) {
    const nextName = window.prompt("Rename Markdown file:", docName);
    if (!nextName || !nextName.trim() || nextName.trim() === docName) return;

    button.disabled = true;
    button.textContent = "RENAMING";

    try {
      const response = await fetch(`/api/markdown/rename/${encodeURIComponent(docId)}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ name: nextName.trim() })
      });
      const data = await response.json();
      if (data.ok) {
        window.location.href = "/markdown";
      } else {
        alert(data.error || "Rename failed");
      }
    } catch (error) {
      alert(error.message || "Rename failed");
    } finally {
      button.disabled = false;
      button.textContent = "RENAME";
    }
  }

  async function deleteDoc(docId, docName, button) {
    const ok = window.confirm(`Delete Markdown file "${docName}"? This cannot be undone.`);
    if (!ok) return;

    button.disabled = true;
    button.textContent = "DELETING";

    try {
      const response = await fetch(`/api/markdown/delete/${encodeURIComponent(docId)}`, { method: "POST" });
      const data = await response.json();
      if (data.ok) {
        button.closest(".markdown-doc-row")?.remove();
      } else {
        alert(data.error || "Delete failed");
      }
    } catch (error) {
      alert(error.message || "Delete failed");
    } finally {
      button.disabled = false;
      button.textContent = "DELETE";
    }
  }

  document.querySelectorAll(".markdown-folder-filter").forEach((button) => {
    button.addEventListener("click", () => {
      if (!filterInput) return;
      filterInput.value = button.dataset.filter || "";
      applyFilter();
    });
  });

  if (filterInput) {
    filterInput.value = getInitialFilter();
    filterInput.addEventListener("input", applyFilter);
    applyFilter();
  }


  document.querySelectorAll(".rename-markdown").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      renameDoc(button.dataset.docId || "", button.dataset.docName || "", button);
    });
  });

  document.querySelectorAll(".delete-markdown").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      deleteDoc(button.dataset.docId || "", button.dataset.docName || "", button);
    });
  });

  archiveButton?.addEventListener("click", () => {
    openArchiveModal(activeArchiveFolder);
  });

  archiveCancel?.addEventListener("click", closeArchiveModal);

  archiveModal?.addEventListener("click", (event) => {
    if (event.target === archiveModal) closeArchiveModal();
  });

  archiveConfirm?.addEventListener("click", () => {
    archiveFolder(activeArchiveFolder);
  });
})();
