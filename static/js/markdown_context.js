(function () {
  const root = document.body.dataset.markdownRoot || "markdown";
  const active = document.body.dataset.markdownContext === "1";
  const libraryKey = "lcars-markdown-library-url";
  const rootLibraryKey = `${libraryKey}:${root}`;

  function url(path) {
    const target = new URL(path, window.location.origin);
    if (root !== "markdown") target.searchParams.set("root", root);
    return `${target.pathname}${target.search}${target.hash}`;
  }

  function validLibraryUrl(saved) {
    if (saved) {
      try {
        const target = new URL(saved, window.location.origin);
        if (target.origin === window.location.origin && target.pathname === "/markdown" &&
            (!active || (target.searchParams.get("root") || "markdown") === root)) {
          return `${target.pathname}${target.search}`;
        }
      } catch { /* Fall back to the current root. */ }
    }
    return "";
  }

  function libraryUrl() {
    return validLibraryUrl(localStorage.getItem(active ? rootLibraryKey : libraryKey)) || url("/markdown");
  }

  function backUrl(fallback) {
    return validLibraryUrl(sessionStorage.getItem(rootLibraryKey)) || fallback;
  }

  window.lcarsMarkdown = { root, url, libraryUrl, backUrl, libraryKey, rootLibraryKey };
})();
