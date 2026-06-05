(function () {
  async function deleteBook(bookId, bookName, button) {
    if (!window.confirm(`Delete book "${bookName}"? This cannot be undone.`)) return;
    button.disabled = true; button.textContent = "DELETING";
    try {
      const response = await fetch(`/api/book/delete/${encodeURIComponent(bookId)}`, { method: "POST" });
      const data = await response.json();
      if (data.ok) button.closest(".book-file-row")?.remove();
      else alert(data.error || "Delete failed");
    } catch (error) { alert(error.message || "Delete failed"); }
    finally { button.disabled = false; button.textContent = "DELETE"; }
  }
  document.querySelectorAll(".delete-book").forEach((button) => {
    button.addEventListener("click", (event) => {
      event.preventDefault(); event.stopPropagation();
      deleteBook(button.dataset.bookId || "", button.dataset.bookName || "", button);
    });
  });
})();
