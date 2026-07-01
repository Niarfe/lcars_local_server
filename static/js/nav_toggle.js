(function () {
  const shell = document.querySelector(".shell");
  const nav = document.querySelector(".nav");
  const toggle = document.getElementById("sidebar-toggle");

  function applyCollapsed(collapsed) {
    if (!shell || !nav) return;
    shell.classList.toggle("nav-collapsed", collapsed);
    localStorage.setItem("lcars-nav-collapsed", collapsed ? "1" : "0");
    if (toggle) toggle.textContent = collapsed ? "NAV" : "SIDE";
  }

  function applyScale(scale) {
    document.documentElement.style.setProperty("--lcars-ui-scale", scale);
    localStorage.setItem("lcars-ui-scale", scale);
  }

  applyCollapsed(localStorage.getItem("lcars-nav-collapsed") === "1");
  applyScale(localStorage.getItem("lcars-ui-scale") || "1");

  if (toggle) {
    toggle.addEventListener("click", () => {
      applyCollapsed(!shell.classList.contains("nav-collapsed"));
    });
  }

  document.querySelectorAll(".ui-scale-option").forEach((button) => {
    button.addEventListener("click", () => {
      applyScale(button.dataset.scale || "1");
    });
  });

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

  async function loadContentRoots() {
    const markdownEl = document.getElementById("settings-markdown-dir");
    const booksEl = document.getElementById("settings-books-dir");
    const soundsEl = document.getElementById("settings-sounds-dir");

    if (!markdownEl && !booksEl && !soundsEl) return;

    try {
      const response = await fetch("/api/content/config");
      const data = await response.json();
      const content = data.content || {};
      if (markdownEl) markdownEl.textContent = content.markdown_dir || "-";
      if (booksEl) booksEl.textContent = content.books_dir || "-";
      if (soundsEl) soundsEl.textContent = content.sounds_dir || "-";
    } catch {
      if (markdownEl) markdownEl.textContent = "unavailable";
      if (booksEl) booksEl.textContent = "unavailable";
      if (soundsEl) soundsEl.textContent = "unavailable";
    }
  }

  loadContentRoots();
})();
