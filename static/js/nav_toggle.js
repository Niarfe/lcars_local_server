(function () {
  const MARKDOWN_LIBRARY_URL_KEY = "lcars-markdown-library-url";
  const shell = document.querySelector(".shell");
  const nav = document.querySelector(".nav");
  const toggle = document.getElementById("sidebar-toggle");
  const hoverMedia = window.matchMedia("(hover: hover) and (pointer: fine)");

  function updateToggle() {
    if (!shell || !toggle) return;
    const collapsed = shell.classList.contains("nav-collapsed");
    const peeking = shell.classList.contains("nav-peeking");
    const label = collapsed
      ? (peeking ? "Keep sidebar open" : "Expand sidebar")
      : "Minimize sidebar";
    toggle.textContent = collapsed ? "NAV" : "SIDE";
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("title", label);
    toggle.setAttribute("aria-expanded", String(!collapsed || peeking));
  }

  function applyPeek(peeking) {
    if (!shell) return;
    shell.classList.toggle("nav-peeking", peeking && shell.classList.contains("nav-collapsed"));
    updateToggle();
  }

  function applyCollapsed(collapsed) {
    if (!shell || !nav) return;
    shell.classList.toggle("nav-collapsed", collapsed);
    shell.classList.remove("nav-peeking");
    localStorage.setItem("lcars-nav-collapsed", collapsed ? "1" : "0");
    updateToggle();
  }

  function applyScale(scale) {
    document.documentElement.style.setProperty("--lcars-ui-scale", scale);
    localStorage.setItem("lcars-ui-scale", scale);
  }

  applyCollapsed(localStorage.getItem("lcars-nav-collapsed") === "1");
  applyScale(localStorage.getItem("lcars-ui-scale") || "1");

  const savedMarkdownUrl = window.lcarsMarkdown.libraryUrl();
  if (savedMarkdownUrl) {
    try {
      const url = new URL(savedMarkdownUrl, window.location.origin);
      if (url.origin === window.location.origin && url.pathname === "/markdown") {
        document.querySelectorAll("[data-markdown-library-link]").forEach((link) => {
          link.href = `${url.pathname}${url.search}`;
        });
      }
    } catch {
      localStorage.removeItem(MARKDOWN_LIBRARY_URL_KEY);
    }
  }

  if (toggle && shell) {
    toggle.addEventListener("click", () => {
      applyCollapsed(!shell.classList.contains("nav-collapsed"));
    });
  }

  if (nav) {
    nav.addEventListener("pointerenter", (event) => {
      if (hoverMedia.matches && event.pointerType !== "touch") applyPeek(true);
    });
    nav.addEventListener("pointerleave", () => {
      const focused = document.activeElement;
      applyPeek(nav.contains(focused) && focused.matches(":focus-visible"));
    });
    nav.addEventListener("focusin", (event) => {
      if (event.target.matches(":focus-visible")) applyPeek(true);
    });
    nav.addEventListener("focusout", (event) => {
      if (!nav.contains(event.relatedTarget)) {
        applyPeek(hoverMedia.matches && nav.matches(":hover"));
      }
    });
    nav.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && shell?.classList.contains("nav-collapsed")) {
        toggle?.focus({ preventScroll: true });
        applyPeek(false);
      }
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
