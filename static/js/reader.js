(function () {
  const bookId = window.__BOOK_ID__;
  const bodyEl = document.getElementById("reader-body");
  const titleEl = document.getElementById("reader-title");
  const surfaceEl = document.getElementById("reader-surface");
  const smallerBtn = document.getElementById("font-smaller");
  const largerBtn = document.getElementById("font-larger");
  const paperBtn = document.getElementById("paper-theme");
  const darkBtn = document.getElementById("dark-theme");

  const fontKey = `reader-font-size:${bookId}`;
  const themeKey = `reader-theme:${bookId}`;
  const scrollKey = `reader-scroll:${bookId}`;

  let fontSize = Number(localStorage.getItem(fontKey) || 20);
  let theme = localStorage.getItem(themeKey) || "paper";

  function applyFontSize() {
    bodyEl.style.fontSize = `${fontSize}px`;
    localStorage.setItem(fontKey, String(fontSize));
  }

  function applyTheme() {
    surfaceEl.classList.toggle("paper-theme", theme === "paper");
    surfaceEl.classList.toggle("dark-reader-theme", theme === "dark");
    localStorage.setItem(themeKey, theme);
  }

  function paragraphsFromText(text) {
    return text
      .split(/\n\s*\n/g)
      .map(part => part.trim())
      .filter(Boolean)
      .map(part => `<p>${part.replace(/\n/g, "<br>")}</p>`)
      .join("");
  }

  async function loadBook() {
    const response = await fetch(`/api/book/${encodeURIComponent(bookId)}`);
    const data = await response.json();

    if (!data.ok) {
      titleEl.textContent = "Book not found";
      bodyEl.innerHTML = "<p>Unable to load this text.</p>";
      return;
    }

    titleEl.textContent = data.name;
    bodyEl.innerHTML = paragraphsFromText(data.text);

    const savedScroll = Number(localStorage.getItem(scrollKey) || 0);
    if (savedScroll > 0) {
      window.scrollTo(0, savedScroll);
    }
  }

  smallerBtn.addEventListener("click", () => {
    fontSize = Math.max(14, fontSize - 1);
    applyFontSize();
  });

  largerBtn.addEventListener("click", () => {
    fontSize = Math.min(30, fontSize + 1);
    applyFontSize();
  });

  paperBtn.addEventListener("click", () => {
    theme = "paper";
    applyTheme();
  });

  darkBtn.addEventListener("click", () => {
    theme = "dark";
    applyTheme();
  });

  window.addEventListener("scroll", () => {
    localStorage.setItem(scrollKey, String(window.scrollY));
  }, { passive: true });

  applyFontSize();
  applyTheme();
  loadBook().catch(() => {
    titleEl.textContent = "Load error";
    bodyEl.innerHTML = "<p>There was a problem loading this text.</p>";
  });
  const deleteBookButton = document.getElementById("delete-book-current");
  if (deleteBookButton) {
    deleteBookButton.addEventListener("click", async () => {
      const bookId = deleteBookButton.dataset.bookId || "";
      const bookName = deleteBookButton.dataset.bookName || "";
      if (!window.confirm(`Delete book "${bookName}"? This cannot be undone.`)) return;
      deleteBookButton.disabled = true; deleteBookButton.textContent = "DELETING";
      try {
        const response = await fetch(`/api/book/delete/${encodeURIComponent(bookId)}`, { method: "POST" });
        const data = await response.json();
        if (data.ok) window.location.href = "/books";
        else alert(data.error || "Delete failed");
      } catch (error) { alert(error.message || "Delete failed"); }
      finally { deleteBookButton.disabled = false; deleteBookButton.textContent = "DELETE"; }
    });
  }
})();

