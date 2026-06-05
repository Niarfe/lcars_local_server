(function () {
  const treeEl = document.getElementById("link-tree");
  const pathInput = document.getElementById("link-path");
  const nameInput = document.getElementById("link-name");
  const urlInput = document.getElementById("link-url");
  const addButton = document.getElementById("add-link");
  const errorEl = document.getElementById("link-error");

  if (!treeEl) return;

  const STATE_KEY = "lcars-link-details-state";
  let tree = window.__INITIAL_LINK_TREE__ || {};

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function loadState() {
    try {
      return JSON.parse(localStorage.getItem(STATE_KEY) || "{}");
    } catch {
      return {};
    }
  }

  function saveState() {
    const state = {};
    treeEl.querySelectorAll("details.link-folder").forEach((details) => {
      state[details.dataset.path || ""] = details.open;
    });
    localStorage.setItem(STATE_KEY, JSON.stringify(state));
  }

  function renderNode(node, depth = 0, path = "") {
    if (!node || typeof node !== "object") return "";
    const state = loadState();

    return Object.entries(node).map(([key, value]) => {
      const nextPath = path ? `${path}/${key}` : key;

      if (typeof value === "string") {
        return `
          <div class="link-item link-leaf" style="--depth:${depth}">
            <a href="${escapeHtml(value)}" target="_blank" rel="noopener noreferrer">
              <span class="link-name">${escapeHtml(key)}</span>
              <span class="link-url">${escapeHtml(value)}</span>
            </a>
          </div>
        `;
      }

      const isOpen = state[nextPath] === true;
      return `
        <details class="link-folder" style="--depth:${depth}" data-path="${escapeHtml(nextPath)}" ${isOpen ? "open" : ""}>
          <summary>${escapeHtml(key)}</summary>
          <div class="link-children">${renderNode(value, depth + 1, nextPath)}</div>
        </details>
      `;
    }).join("");
  }

  function installDetailsListeners() {
    treeEl.querySelectorAll("details.link-folder").forEach((details) => {
      details.addEventListener("toggle", saveState);
    });
  }

  function ensureControls() {
    if (document.getElementById("close-all-links")) return;

    const controls = document.createElement("div");
    controls.className = "link-controls";
    controls.innerHTML = `<button id="close-all-links" class="action" type="button">CLOSE ALL</button>`;
    treeEl.before(controls);

    document.getElementById("close-all-links").addEventListener("click", () => {
      treeEl.querySelectorAll("details.link-folder").forEach((details) => {
        details.open = false;
      });
      saveState();
    });
  }

  function renderTree() {
    const hasItems = tree && Object.keys(tree).length > 0;
    treeEl.innerHTML = hasItems
      ? renderNode(tree)
      : `<div class="empty-state"><div class="empty-title">NO LINKS FOUND</div><div class="subtle">Add a folder path, link name, and URL.</div></div>`;
    ensureControls();
    installDetailsListeners();
  }

  async function addLink() {
    if (!pathInput || !nameInput || !urlInput || !addButton || !errorEl) return;

    const payload = {
      path: pathInput.value.trim(),
      name: nameInput.value.trim(),
      url: urlInput.value.trim()
    };

    errorEl.textContent = "";

    if (!payload.name || !payload.url) {
      errorEl.textContent = "NAME AND URL REQUIRED";
      return;
    }

    addButton.disabled = true;
    addButton.textContent = "ADDING";

    try {
      const response = await fetch("/api/links/add", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload)
      });
      const data = await response.json();

      if (!data.ok) {
        errorEl.textContent = data.error || "ADD FAILED";
        return;
      }

      tree = data.links || {};
      nameInput.value = "";
      urlInput.value = "";

      // Open the parent path of the newly added link.
      const state = loadState();
      const parts = payload.path.replace(/^\/+|\/+$/g, "").split("/").filter(Boolean);
      let current = "";
      parts.forEach((part) => {
        current = current ? `${current}/${part}` : part;
        state[current] = true;
      });
      localStorage.setItem(STATE_KEY, JSON.stringify(state));

      renderTree();
    } catch (error) {
      errorEl.textContent = error.message || "ADD FAILED";
    } finally {
      addButton.disabled = false;
      addButton.textContent = "ADD LINK";
    }
  }

  if (addButton) addButton.addEventListener("click", addLink);
  [pathInput, nameInput, urlInput].forEach((input) => {
    if (!input) return;
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter") addLink();
    });
  });

  renderTree();
})();
