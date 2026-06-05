(function () {
  const filterInput = document.getElementById("markdown-filter");
  const rows = Array.from(document.querySelectorAll(".markdown-doc-row"));
  const FILTER_KEY = "lcars-markdown-filter";

  function applyFilter() {
    const query = (filterInput.value || "").trim().toLowerCase();
    localStorage.setItem(FILTER_KEY, query);

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


document.querySelectorAll(".actions-toggle").forEach((button) => {
  button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();

    const menu = button.parentElement.querySelector(".actions-menu");
    document.querySelectorAll(".actions-menu.open").forEach((m) => {
      if (m !== menu) m.classList.remove("open");
    });

    if (menu) menu.classList.toggle("open");
  });
});

document.addEventListener("click", () => {
  document.querySelectorAll(".actions-menu.open").forEach((menu) => {
    menu.classList.remove("open");
  });
});
