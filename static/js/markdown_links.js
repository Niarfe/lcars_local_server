(function () {
  const dialog = document.getElementById("markdown-peek-dialog");
  if (!dialog) return;
  const frame = document.getElementById("markdown-peek-frame");
  const title = document.getElementById("markdown-peek-title");
  const pathLabel = document.getElementById("markdown-peek-path");
  const position = document.getElementById("markdown-peek-position");
  const previousButton = document.getElementById("markdown-peek-previous");
  const nextButton = document.getElementById("markdown-peek-next");
  const peekStatus = document.getElementById("markdown-peek-status");
  const copyButton = document.getElementById("markdown-peek-copy");
  const openLink = document.getElementById("markdown-peek-open");
  const editLink = document.getElementById("markdown-peek-edit");
  const closeButton = document.getElementById("markdown-peek-close");
  const status = document.getElementById("markdown-link-status");
  let returnFocus = null;
  let statusTimer;
  let entries = [];
  let activeIndex = -1;

  function documentUrl(value) {
    try {
      const url = new URL(value, window.location.href);
      const path = url.pathname === "/md/view" ? url.searchParams.get("path") || "" : decodeURIComponent(url.pathname);
      if (url.origin === window.location.origin &&
          (url.pathname === "/md/view" || url.pathname.startsWith("/md/view/")) &&
          path.toLowerCase().endsWith(".md")) return url;
    } catch { /* Leave other links alone. */ }
    return null;
  }

  function announce(message) {
    clearTimeout(statusTimer);
    const target = dialog.open ? peekStatus : status;
    target.textContent = message;
    statusTimer = setTimeout(() => {
      target.textContent = target === peekStatus && dialog.open ? peekHint() : "";
    }, 5000);
  }

  function peekHint() {
    return entries.length > 1 ? "← / → to browse · Esc to close" : "Esc to close";
  }

  function closeMenu(button) {
    button.closest(".actions-menu")?.classList.remove("open");
  }

  function fallbackCopy(text) {
    const previousFocus = document.activeElement;
    const input = document.createElement("textarea");
    input.value = text;
    input.readOnly = true;
    input.className = "markdown-copy-buffer";
    // A modal dialog makes the rest of the page inert, so copy inside it.
    (dialog.open ? dialog : document.body).append(input);
    input.select();
    try {
      return document.execCommand("copy");
    } finally {
      input.remove();
      previousFocus?.focus({ preventScroll: true });
    }
  }

  async function copyLink(button) {
    const url = documentUrl(button.dataset.copyMarkdownLink);
    if (!url) return;
    const name = (button.dataset.docName || "Document").replace(/\s+/g, " ").trim();
    const label = name.replace(/[\\`*_[\]<>&]/g, "\\$&");
    // Keep the link on this LCARS server even when its hostname or port changes.
    const destination = `${url.pathname}${url.search}${url.hash}`.replace(/\(/g, "%28").replace(/\)/g, "%29");
    const text = `[${label}](${destination})`;
    let copied = false;
    try {
      await navigator.clipboard.writeText(text);
      copied = true;
    } catch {
      try { copied = fallbackCopy(text); } catch { /* Offer manual copying below. */ }
    }
    if (copied) {
      announce("Markdown link copied. Paste it into your document.");
    } else {
      window.prompt("Copy this Markdown link:", text);
      announce("Markdown link ready for manual copying.");
    }
    closeMenu(button);
  }

  function updateDocumentLinks(url, name) {
    const destination = `${url.pathname}${url.search}${url.hash}`;
    openLink.href = destination;
    copyButton.dataset.copyMarkdownLink = destination;
    copyButton.dataset.docName = name;
    const editUrl = new URL(url);
    editUrl.pathname = url.pathname.replace(/^\/md\/view(?=\/|$)/, "/md/edit");
    editUrl.hash = "";
    editLink.href = `${editUrl.pathname}${editUrl.search}`;
    pathLabel.textContent = url.searchParams.get("path") || decodeURIComponent(url.pathname.replace(/^\/md\/view\//, ""));
    pathLabel.title = pathLabel.textContent;
  }

  function showPeek(index) {
    if (index < 0 || index >= entries.length || index === activeIndex) return;
    activeIndex = index;
    const { url, name } = entries[index];
    title.textContent = name;
    title.title = name;
    position.textContent = `${index + 1} of ${entries.length}`;
    previousButton.disabled = index === 0;
    nextButton.disabled = index === entries.length - 1;
    updateDocumentLinks(url, name);
    copyButton.disabled = true;
    clearTimeout(statusTimer);
    peekStatus.textContent = "Loading document…";
    frame.classList.add("is-loading");
    frame.title = `Preview of ${name}`;
    const previewUrl = new URL(url);
    previewUrl.pathname = url.pathname.replace(/^\/md\/view(?=\/|$)/, "/md/peek");
    // Appending the theme preserves readable slashes in the filesystem path.
    previewUrl.search += `${previewUrl.search ? "&" : "?"}theme=${encodeURIComponent(localStorage.getItem("lcars-markdown-theme") || "paper")}`;
    frame.src = `${previewUrl.pathname}${previewUrl.search}${previewUrl.hash}`;
    if (!dialog.open) dialog.showModal();
  }

  function peek(button) {
    const scope = button.closest("#markdown-doc-list, #markdown-body");
    const buttons = scope ? Array.from(scope.querySelectorAll("[data-peek-markdown]")) : [button];
    // Read the live DOM order so sorting and name/GREP filtering carry into PEEK.
    entries = buttons.filter((candidate) => candidate.getClientRects().length > 0).flatMap((candidate) => {
      const url = documentUrl(candidate.dataset.peekMarkdown);
      return url ? [{ url, name: candidate.dataset.docName || "Document", button: candidate }] : [];
    });
    const index = entries.findIndex((entry) => entry.button === button);
    if (index < 0) return;
    const menu = button.closest(".actions-menu");
    returnFocus = menu?.parentElement.querySelector(".actions-toggle") || button;
    closeMenu(button);
    activeIndex = -1;
    showPeek(index);
  }

  function handlePeekKey(event) {
    if (!dialog.open || event.defaultPrevented || event.isComposing) return;
    if (event.key === "Escape") {
      event.preventDefault();
      dialog.close();
      return;
    }
    if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey ||
        event.target.closest?.("input, textarea, select, [contenteditable]")) return;
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      showPeek(activeIndex + (event.key === "ArrowLeft" ? -1 : 1));
    }
  }

  previousButton.addEventListener("click", () => showPeek(activeIndex - 1));
  nextButton.addEventListener("click", () => showPeek(activeIndex + 1));
  document.addEventListener("keydown", handlePeekKey);

  document.addEventListener("click", (event) => {
    const copy = event.target.closest("[data-copy-markdown-link]");
    if (copy) {
      event.preventDefault();
      copyLink(copy);
      return;
    }
    const preview = event.target.closest("[data-peek-markdown]");
    if (preview) {
      event.preventDefault();
      peek(preview);
    }
  });

  frame.addEventListener("load", () => {
    if (!dialog.open) return;
    const content = frame.contentDocument;
    if (content?.URL === "about:blank") return;
    if (content) {
      const loadedUrl = new URL(content.URL);
      const expectedUrl = new URL(frame.src);
      loadedUrl.hash = expectedUrl.hash = "";
      if (loadedUrl.href !== expectedUrl.href) return;
    }
    const previewDocument = content?.querySelector(".markdown-peek-document");
    if (!previewDocument) {
      peekStatus.textContent = "Could not preview this document. It may have moved or its folder may be unavailable.";
      return;
    }
    // Old links can still be peeked; copying from the preview uses the real path.
    const canonicalUrl = documentUrl(previewDocument.dataset.documentUrl);
    if (canonicalUrl) {
      canonicalUrl.hash = new URL(frame.src).hash;
      updateDocumentLinks(canonicalUrl, entries[activeIndex].name);
    }
    copyButton.disabled = false;
    peekStatus.textContent = peekHint();
    frame.classList.remove("is-loading");
    // Keep fragment links within the preview; other links open a separate tab.
    content.querySelectorAll('a[href^="#"]').forEach((link) => { link.target = "_self"; });
    // Keyboard browsing also works while reading inside the sandboxed iframe.
    content.addEventListener("keydown", handlePeekKey);
  });

  closeButton.addEventListener("click", () => dialog.close());
  dialog.addEventListener("click", (event) => {
    if (event.target === dialog) {
      const bounds = dialog.getBoundingClientRect();
      if (event.clientX < bounds.left || event.clientX > bounds.right ||
          event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
    }
  });
  dialog.addEventListener("close", () => {
    clearTimeout(statusTimer);
    frame.removeAttribute("src");
    frame.classList.add("is-loading");
    entries = [];
    activeIndex = -1;
    returnFocus?.focus({ preventScroll: true });
  });

  document.querySelectorAll("#markdown-body a[href]").forEach((link) => {
    if (!documentUrl(link.getAttribute("href")) || link.closest("pre, code")) return;
    const name = link.textContent.trim() || link.querySelector("img")?.alt || "Document";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "markdown-peek-button";
    button.textContent = "PEEK";
    button.dataset.peekMarkdown = link.getAttribute("href");
    button.dataset.docName = name;
    button.title = `Preview ${name} without leaving this page`;
    button.setAttribute("aria-label", `Peek at ${name}`);
    button.setAttribute("aria-haspopup", "dialog");
    link.after(button);
  });
})();
