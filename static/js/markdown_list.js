(function () {
  const MARKDOWN_LIBRARY_URL_KEY = "lcars-markdown-library-url";
  const filterInput = document.getElementById("markdown-filter");
  const rows = Array.from(document.querySelectorAll(".markdown-doc-row"));
  const docList = document.getElementById("markdown-doc-list");
  const fullPathsToggle = document.getElementById("markdown-full-paths");
  const fullPathsKey = "lcars-markdown-full-paths";
  const rowLabels = rows.map((row) => {
    const title = row.querySelector(".markdown-doc-title");
    const path = row.querySelector(".markdown-doc-path");
    return { row, title, path, originalTitle: title.textContent };
  });
  const pathSortedRows = [...rows].sort((first, second) => {
    const firstPath = first.dataset.path || "";
    const secondPath = second.dataset.path || "";
    return firstPath < secondPath ? -1 : firstPath > secondPath ? 1 : 0;
  });
  const archiveButton = document.getElementById("archive-markdown-context");
  const openFolderButton = document.getElementById("open-markdown-library-folder");
  const archiveModal = document.getElementById("archive-modal");
  const archiveSummary = document.getElementById("archive-summary");
  const archiveStatus = document.getElementById("archive-status");
  const archiveConfirm = document.getElementById("archive-confirm");
  const archiveCancel = document.getElementById("archive-cancel");
  const searchForm = document.getElementById("markdown-search-form");
  const searchModeInput = document.getElementById("markdown-search-mode");
  const searchModeButtons = Array.from(document.querySelectorAll("[data-search-mode]"));
  let searchMode = searchForm?.dataset.mode === "grep" ? "grep" : "names";
  const activeArchiveFolder = archiveButton?.dataset.folder || "";

  function applyFullPaths() {
    const enabled = Boolean(fullPathsToggle?.checked);
    rowLabels.forEach(({ title, path, originalTitle }) => {
      title.textContent = enabled ? path.textContent : originalTitle;
      path.classList.toggle("hidden", enabled);
    });
    if (docList) {
      const orderedRows = document.createDocumentFragment();
      (enabled ? pathSortedRows : rows).forEach((row) => {
        if (row.parentNode === docList) orderedRows.append(row);
      });
      docList.append(orderedRows);
    }
  }

  if (fullPathsToggle) {
    fullPathsToggle.checked = localStorage.getItem(fullPathsKey) === "1";
    applyFullPaths();
    fullPathsToggle.addEventListener("change", () => {
      localStorage.setItem(fullPathsKey, fullPathsToggle.checked ? "1" : "0");
      applyFullPaths();
    });
  }

  function rememberCurrentLibraryUrl() {
    if (window.location.pathname !== "/markdown") return;
    localStorage.setItem(
      MARKDOWN_LIBRARY_URL_KEY,
      `${window.location.pathname}${window.location.search}`
    );
    localStorage.setItem(window.lcarsMarkdown.rootLibraryKey, `${window.location.pathname}${window.location.search}`);
    sessionStorage.setItem(window.lcarsMarkdown.rootLibraryKey, `${window.location.pathname}${window.location.search}`);
  }

  function encodeDocPath(docId) {
    return String(docId || "")
      .split("/")
      .map((part) => encodeURIComponent(part))
      .join("/");
  }

  function updateNameSearchUrl(query) {
    const url = new URL(window.location.href);
    url.searchParams.delete("mode");
    if (query) url.searchParams.set("q", query);
    else url.searchParams.delete("q");
    window.history.replaceState({}, "", url);
    rememberCurrentLibraryUrl();
  }

  function applyFilter() {
    const query = (filterInput.value || "").trim().toLowerCase();
    updateNameSearchUrl((filterInput.value || "").trim());

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

  function submitSearchMode(nextMode) {
    if (!searchForm || !searchModeInput) return;
    searchMode = nextMode === "grep" ? "grep" : "names";
    searchModeInput.value = searchMode;
    searchForm.submit();
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
      const response = await fetch(window.lcarsMarkdown.url(`/api/markdown/archive/preview/${encodeURIComponent(folder)}`));
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
      const response = await fetch(window.lcarsMarkdown.url(`/api/markdown/archive/${encodeURIComponent(folder)}`), { method: "POST" });
      const data = await response.json();
      if (!data.ok) {
        if (archiveStatus) archiveStatus.textContent = data.error || "ARCHIVE FAILED";
        return;
      }
      const commits = (data.archive?.commits || []).map((commit) => commit.hash).filter(Boolean);
      if (archiveStatus) archiveStatus.textContent = commits.length ? `ARCHIVED: ${commits.join(", ")}` : "ARCHIVED";
      localStorage.removeItem(MARKDOWN_LIBRARY_URL_KEY);
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
      const response = await fetch(window.lcarsMarkdown.url(`/api/markdown/rename/${encodeDocPath(docId)}`), {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ name: nextName.trim() })
      });
      const data = await response.json();
      if (data.ok) {
        window.location.reload();
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
    const ok = window.confirm(`Delete Markdown file "${docName}"?\n${document.body.dataset.markdownRootPath}/${docId}\n\nThis cannot be undone.`);
    if (!ok) return;

    button.disabled = true;
    button.textContent = "DELETING";

    try {
      const response = await fetch(window.lcarsMarkdown.url(`/api/markdown/delete/${encodeDocPath(docId)}`), { method: "POST" });
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

  if (filterInput && searchMode === "names") {
    filterInput.addEventListener("input", applyFilter);
    applyFilter();
  }

  searchForm?.addEventListener("submit", (event) => {
    if (searchMode !== "names") return;
    event.preventDefault();
    applyFilter();
  });

  searchModeButtons.forEach((button) => {
    button.addEventListener("click", () => {
      const nextMode = button.dataset.searchMode || "names";
      if (nextMode === "names" && searchMode === "names") {
        applyFilter();
        return;
      }
      submitSearchMode(nextMode);
    });
  });

  document.querySelectorAll("[data-folder-link]").forEach((link) => {
    link.addEventListener("click", () => {
      if (!filterInput) return;
      const url = new URL(link.href, window.location.href);
      const query = filterInput.value.trim();
      if (query) url.searchParams.set("q", query);
      else url.searchParams.delete("q");
      if (searchMode === "grep") url.searchParams.set("mode", "grep");
      else url.searchParams.delete("mode");
      link.href = url.toString();
    });
  });

  rememberCurrentLibraryUrl();

  openFolderButton?.addEventListener("click", async () => {
    openFolderButton.disabled = true;
    openFolderButton.textContent = "OPENING";
    try {
      const response = await fetch(window.lcarsMarkdown.url("/api/markdown/open-folder"), {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder: openFolderButton.dataset.folder || "" })
      });
      const data = await response.json();
      if (!data.ok) alert(data.error || "Could not open folder");
    } catch (error) {
      alert(error.message || "Could not open folder");
    } finally {
      openFolderButton.disabled = false;
      openFolderButton.textContent = "FINDER";
    }
  });

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
