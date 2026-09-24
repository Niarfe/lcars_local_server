(function () {
  const titleInput =
    document.getElementById("new-md-title") ||
    document.getElementById("markdown-title");

  const createButton =
    document.getElementById("create-md") ||
    document.getElementById("create-markdown");

  const errorEl =
    document.getElementById("new-md-error") ||
    document.getElementById("markdown-error");

  const contextEl = document.getElementById("markdown-folder-context");

  function encodeDocPath(path) {
    return String(path || "")
      .split("/")
      .map((part) => encodeURIComponent(part))
      .join("/");
  }

  if (!titleInput || !createButton) return;

  const params = new URLSearchParams(window.location.search);
  const folder = (params.get("folder") || "").replace(/^\/+|\/+$/g, "");

  if (folder) {
    if (contextEl) contextEl.textContent = `NEW DOCUMENT WILL BE CREATED IN: ${folder}/`;
    titleInput.placeholder = `${folder}/new document`;
  } else if (contextEl) {
    contextEl.textContent = "";
  }

  async function createMarkdown() {
    const title = titleInput.value.trim();
    if (errorEl) errorEl.textContent = "";

    if (!title) {
      if (errorEl) errorEl.textContent = "TITLE REQUIRED";
      return;
    }

    createButton.disabled = true;
    const oldText = createButton.textContent;
    createButton.textContent = "CREATING";

    try {
      const response = await fetch("/api/markdown/create", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ title, folder })
      });

      const data = await response.json();

      if (!data.ok) {
        if (errorEl) errorEl.textContent = data.error || "CREATE FAILED";
        return;
      }

      window.location.href = `/md/edit/${encodeDocPath(data.id)}`;
    } catch (error) {
      if (errorEl) errorEl.textContent = error.message || "CREATE FAILED";
    } finally {
      createButton.disabled = false;
      createButton.textContent = oldText || "CREATE MARKDOWN FILE";
    }
  }

  createButton.addEventListener("click", createMarkdown);
  titleInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") createMarkdown();
  });
})();
