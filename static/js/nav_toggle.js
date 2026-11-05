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
      : "Collapse sidebar";
    toggle.setAttribute("aria-label", label);
    toggle.setAttribute("title", label);
    toggle.setAttribute("aria-expanded", String(!collapsed || peeking));
  }

  function applyPeek(peeking) {
    if (!shell) return;
    const visible = (peeking || Boolean(nav?.querySelector(".sidebar-popover:popover-open"))) && shell.classList.contains("nav-collapsed");
    const changed = shell.classList.contains("nav-peeking") !== visible;
    shell.classList.toggle("nav-peeking", visible);
    updateToggle();
    if (changed) document.dispatchEvent(new Event("sidebar-visibility-change"));
  }

  function applyCollapsed(collapsed) {
    if (!shell || !nav) return;
    nav.querySelectorAll(".sidebar-popover:popover-open").forEach((menu) => menu.hidePopover());
    shell.classList.toggle("nav-collapsed", collapsed);
    shell.classList.remove("nav-peeking");
    localStorage.setItem("lcars-nav-collapsed", collapsed ? "1" : "0");
    updateToggle();
    document.dispatchEvent(new Event("sidebar-visibility-change"));
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
      if (nav.querySelector(".sidebar-popover:popover-open")) return;
      if (event.key === "Escape" && shell?.classList.contains("nav-collapsed")) {
        toggle?.focus({ preventScroll: true });
        applyPeek(false);
      }
    });
  }

  document.querySelectorAll("[data-sidebar-popover]").forEach((button) => {
    const menu = document.getElementById(button.getAttribute("popovertarget"));
    if (!menu) return;

    function positionMenu() {
      if (!menu.matches(":popover-open")) return;
      const anchor = button.getBoundingClientRect();
      const margin = 12;
      const gap = 8;
      const viewportWidth = document.documentElement.clientWidth;
      const below = window.innerHeight - anchor.bottom - gap - margin;
      const above = anchor.top - gap - margin;
      const dropdown = button.dataset.sidebarPopover === "below";
      const openAbove = dropdown && below < 200 && above > below;
      const available = dropdown ? (openAbove ? above : below) : window.innerHeight - margin * 2;
      menu.style.maxHeight = `${Math.max(0, Math.min(480, available))}px`;
      const width = menu.offsetWidth;
      const height = menu.offsetHeight;
      let left = button.dataset.sidebarPopover === "right" ? anchor.right + gap : anchor.left;
      let top = dropdown ? (openAbove ? anchor.top - gap - height : anchor.bottom + gap) : anchor.top;
      left = Math.max(margin, Math.min(left, viewportWidth - width - margin));
      top = Math.max(margin, Math.min(top, window.innerHeight - height - margin));
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
    }

    function focusItem(item) {
      if (!item) return;
      item.focus({ preventScroll: true });
      const viewport = item.closest(".markdown-roots-list") || menu;
      const bounds = viewport.getBoundingClientRect();
      const row = item.getBoundingClientRect();
      if (row.top < bounds.top) viewport.scrollTop -= bounds.top - row.top;
      else if (row.bottom > bounds.bottom) viewport.scrollTop += row.bottom - bounds.bottom;
    }

    menu.addEventListener("toggle", (event) => {
      const open = event.newState === "open";
      button.setAttribute("aria-expanded", String(open));
      if (open) {
        positionMenu();
        const selected = menu.querySelector("a[aria-current]") || menu.querySelector("a, button");
        focusItem(selected);
      }
      const focused = document.activeElement;
      applyPeek(nav?.matches(":hover") || (nav?.contains(focused) && focused.matches(":focus-visible")));
    });
    button.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") {
        event.preventDefault();
        menu.showPopover();
      }
    });
    menu.addEventListener("keydown", (event) => {
      const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
      if (!keys.includes(event.key)) return;
      const items = Array.from(menu.querySelectorAll("a[href], button:not(:disabled)"));
      if (!items.length) return;
      event.preventDefault();
      const index = items.indexOf(document.activeElement);
      const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1
        : (index + (event.key === "ArrowDown" ? 1 : -1) + items.length) % items.length;
      focusItem(items[next]);
    });
    // Tab follows the links and eject buttons naturally; leaving closes the panel.
    menu.addEventListener("focusout", (event) => {
      if (!menu.contains(event.relatedTarget) && event.relatedTarget !== button && menu.matches(":popover-open")) {
        menu.hidePopover();
      }
    });
    window.addEventListener("resize", positionMenu);
    window.addEventListener("scroll", positionMenu, { passive: true, capture: true });
  });

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
