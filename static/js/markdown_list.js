(function () {
  const filterInput = document.getElementById("markdown-filter");
  const rows = Array.from(document.querySelectorAll(".markdown-doc-row"));
  const FILTER_KEY = "lcars-markdown-filter";

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

  function applyFilter() {
    const query = (filterInput.value || "").trim().toLowerCase();
    localStorage.setItem(FILTER_KEY, query);
    updateNewDocumentLink(query);

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
    filterInput.value = localStorage.getItem(FILTER_KEY) || "";
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
})();
