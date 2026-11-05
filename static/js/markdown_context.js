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

  function validLibraryUrl(saved, expectedRoot = active ? root : null) {
    if (saved) {
      try {
        const target = new URL(saved, window.location.origin);
        if (target.origin === window.location.origin && target.pathname === "/markdown" &&
            (expectedRoot === null || (target.searchParams.get("root") || "markdown") === expectedRoot)) {
          return `${target.pathname}${target.search}`;
        }
      } catch { /* Fall back to the current root. */ }
    }
    return "";
  }

  function libraryUrlForRoot(rootId) {
    const fallback = new URL("/markdown", window.location.origin);
    if (rootId !== "markdown") fallback.searchParams.set("root", rootId);
    return validLibraryUrl(localStorage.getItem(`${libraryKey}:${rootId}`), rootId) || `${fallback.pathname}${fallback.search}`;
  }

  function libraryUrl() {
    return validLibraryUrl(localStorage.getItem(active ? rootLibraryKey : libraryKey)) || url("/markdown");
  }

  function backUrl(fallback) {
    return validLibraryUrl(sessionStorage.getItem(rootLibraryKey)) || fallback;
  }

  window.lcarsMarkdown = { root, url, libraryUrl, libraryUrlForRoot, backUrl, libraryKey, rootLibraryKey };
})();
