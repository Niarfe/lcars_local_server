(function () {
  const viewport = document.getElementById("youtube-tag-scroll");
  if (!viewport) return;
  const key = "lcars-youtube-sidebar";
  const branches = Array.from(viewport.querySelectorAll("[data-youtube-branch]"));
  let saved;
  try { saved = JSON.parse(localStorage.getItem(key)); } catch { /* Use the initial tree. */ }
  const expanded = new Set(Array.isArray(saved?.expanded) ? saved.expanded : []);
  let selectionChanged = saved?.selection !== viewport.dataset.selection;
  for (const branch of branches) {
    branch.open = expanded.has(branch.dataset.youtubeBranch)
      || (selectionChanged && branch.dataset.reveal === "true");
  }

  let restoring = false;
  let restoreRevision = 0;
  function remember() {
    if (restoring || !viewport.clientHeight) return;
    try {
      saved = {
        expanded: branches.filter((branch) => branch.open).map((branch) => branch.dataset.youtubeBranch),
        selection: viewport.dataset.selection,
        top: viewport.scrollTop,
      };
      localStorage.setItem(key, JSON.stringify(saved));
    } catch { /* Navigation still works when browser storage is unavailable. */ }
  }

  async function restoreScroll() {
    const revision = ++restoreRevision;
    if (!viewport.clientHeight) return;
    restoring = true;
    const top = Number.isFinite(saved?.top) ? Math.max(0, saved.top) : 0;
    function position() {
      viewport.scrollTop = top;
      if (selectionChanged) {
        const current = viewport.querySelector('[aria-current="page"]');
        if (current) {
          const bounds = viewport.getBoundingClientRect();
          const row = current.getBoundingClientRect();
          if (row.top < bounds.top) viewport.scrollTop -= bounds.top - row.top + 4;
          else if (row.bottom > bounds.bottom) viewport.scrollTop += row.bottom - bounds.bottom + 4;
        }
      }
    }
    position();
    // The rail animates its width. Restore again after labels stop reflowing.
    const animations = [viewport.closest(".shell"), viewport.closest(".nav")]
      .flatMap((element) => element?.getAnimations() || []);
    await Promise.all(animations.map((animation) => animation.finished.catch(() => {})));
    await new Promise(requestAnimationFrame);
    if (revision !== restoreRevision || !viewport.clientHeight) return;
    position();
    selectionChanged = false;
    restoring = false;
    remember();
  }

  branches.forEach((branch) => branch.addEventListener("toggle", remember));
  viewport.addEventListener("click", (event) => {
    const link = event.target.closest("[data-youtube-tag]");
    const branch = link?.closest("summary")?.parentElement;
    if (branch?.matches("[data-youtube-branch]")) branch.open = true;
    remember();
  });
  viewport.addEventListener("scroll", remember, { passive: true });
  viewport.addEventListener("keydown", (event) => {
    if (event.target !== viewport) return;
    const steps = { ArrowDown: 40, ArrowUp: -40, PageDown: viewport.clientHeight * 0.9, PageUp: -viewport.clientHeight * 0.9 };
    if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      viewport.scrollTop = event.key === "Home" ? 0 : viewport.scrollHeight;
    } else if (event.key in steps) {
      event.preventDefault();
      viewport.scrollTop += steps[event.key];
    }
  });
  window.addEventListener("pagehide", remember);
  window.addEventListener("pageshow", restoreScroll);
  document.addEventListener("sidebar-visibility-change", restoreScroll);
  restoreScroll();
})();
