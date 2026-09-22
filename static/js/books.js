(function () {
  const filterInput = document.getElementById("book-filter");
  const filterEmpty = document.getElementById("book-filter-empty");

  function bookRows() {
    return Array.from(document.querySelectorAll("[data-book-search]"));
  }

  function applyBookFilter() {
    const query = (filterInput?.value || "").trim().toLowerCase();
    let visibleRows = 0;

    bookRows().forEach((row) => {
      const matches = !query || (row.dataset.bookSearch || "").includes(query);
      row.classList.toggle("hidden", !matches);
      if (matches) visibleRows += 1;
    });

    if (filterEmpty) {
      filterEmpty.classList.toggle("hidden", !query || visibleRows > 0);
    }
  }

  async function deleteBook(bookId, bookName, button) {
    if (!window.confirm(`Delete book "${bookName}"? This cannot be undone.`)) return;
    button.disabled = true;
    button.textContent = "DELETING";
    try {
      const response = await fetch(`/api/book/delete/${encodeURIComponent(bookId)}`, { method: "POST" });
      const data = await response.json();
      if (data.ok) {
        button.closest(".book-file-row")?.remove();
        applyBookFilter();
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

  async function openS3Book(bookId, button) {
    const row = button.closest(".s3-book-row");
    const openButtons = Array.from(row?.querySelectorAll(".open-s3-book") || [button]);
    const actionButton = row?.querySelector(".book-actions .open-s3-book") || button;
    const originalText = actionButton.textContent;
    const stateEl = row?.querySelector(".s3-cache-state");

    openButtons.forEach((openButton) => {
      openButton.disabled = true;
    });
    actionButton.textContent = actionButton.dataset.bookCached === "true" ? "OPENING" : "DOWNLOADING";

    try {
      const response = await fetch(`/api/s3/book/${encodeURIComponent(bookId)}/open`, { method: "POST" });
      const data = await response.json();
      if (!data.ok) {
        alert(data.error || "Open failed");
        return;
      }

      openButtons.forEach((openButton) => {
        openButton.dataset.bookCached = "true";
      });
      if (stateEl) {
        stateEl.textContent = data.downloaded ? "DOWNLOADED" : "LOCAL";
        stateEl.classList.remove("alt");
      }
    } catch (error) {
      alert(error.message || "Open failed");
    } finally {
      openButtons.forEach((openButton) => {
        openButton.disabled = false;
      });
      actionButton.textContent = originalText;
    }
  }

  filterInput?.addEventListener("input", applyBookFilter);

  document.querySelectorAll(".open-s3-book").forEach((button) => {
    button.addEventListener("click", () => {
      openS3Book(button.dataset.bookId || "", button);
    });
  });

  document.querySelectorAll(".delete-book").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      deleteBook(button.dataset.bookId || "", button.dataset.bookName || "", button);
    });
  });

  applyBookFilter();
})();
