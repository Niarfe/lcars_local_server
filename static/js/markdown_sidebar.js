(function () {
  const context = window.lcarsMarkdown;
  function updateRootLinks() {
    document.querySelectorAll("[data-markdown-root-link]").forEach((link) => {
      link.href = context.libraryUrlForRoot(link.dataset.markdownRootLink);
    });
  }
  updateRootLinks();
  document.getElementById("markdown-roots-menu")?.addEventListener("beforetoggle", (event) => {
    if (event.newState === "open") updateRootLinks();
  });

  const folders = document.getElementById("markdown-folder-scroll");
  if (!folders) return;
  const scrollKey = `lcars-markdown-sidebar:${context.root}`;
  const folder = folders.dataset.navigationFolder ?? folders.dataset.currentFolder;
  let restoring = false;

  function restoreScroll() {
    // A collapsed rail has no folder viewport; restore when it opens instead.
    if (!folders.clientHeight) return;
    let saved;
    try {
      saved = JSON.parse(localStorage.getItem(scrollKey));
    } catch { /* Ignore an invalid saved position. */ }
    restoring = true;
    if (saved?.folder === folder && Number.isFinite(saved.top)) {
      folders.scrollTop = Math.max(0, saved.top);
    } else {
      const current = folders.querySelector('[aria-current="page"]');
      if (current) folders.scrollTop = Math.max(0, current.offsetTop - folders.offsetTop - 8);
    }
    requestAnimationFrame(() => { restoring = false; });
  }

  function rememberScroll() {
    if (restoring || !folders.clientHeight) return;
    localStorage.setItem(scrollKey, JSON.stringify({ folder, top: folders.scrollTop }));
  }

  folders.addEventListener("scroll", rememberScroll, { passive: true });
  folders.addEventListener("keydown", (event) => {
    if (event.target !== folders) return;
    const steps = { ArrowDown: 40, ArrowUp: -40, PageDown: folders.clientHeight * 0.9, PageUp: -folders.clientHeight * 0.9 };
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      folders.scrollTop = event.key === "Home" ? 0 : folders.scrollHeight;
    } else if (event.key in steps) {
      event.preventDefault();
      folders.scrollTop += steps[event.key];
    }
  });
  window.addEventListener("pagehide", rememberScroll);
  window.addEventListener("pageshow", restoreScroll);
  document.addEventListener("sidebar-visibility-change", restoreScroll);
  restoreScroll();
})();
