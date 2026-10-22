(function () {
  const dialog = document.getElementById("markdown-mount-dialog");
  const openButton = document.getElementById("mount-markdown-folder");
  if (!dialog || !openButton) return;
  const folders = document.getElementById("markdown-mount-folders");
  const pathInput = document.getElementById("markdown-mount-path");
  const nameInput = document.getElementById("markdown-mount-label");
  const selection = document.getElementById("markdown-mount-selection");
  const status = document.getElementById("markdown-mount-status");
  const confirm = document.getElementById("markdown-mount-confirm");
  const cancel = document.getElementById("markdown-mount-cancel");
  const up = document.getElementById("markdown-mount-up");
  const hidden = document.getElementById("markdown-mount-hidden");
  let listing = null;
  let selectedPath = "";
  let requestNumber = 0;
  let mounting = false;

  function selectFolder(path, name, button, displayPath = path) {
    selectedPath = path;
    nameInput.value = name;
    selection.textContent = displayPath;
    folders.querySelectorAll("[aria-pressed]").forEach((item) => {
      item.setAttribute("aria-pressed", String(item === button));
    });
    confirm.disabled = false;
  }

  async function browse(path = "") {
    const token = ++requestNumber;
    selectedPath = "";
    confirm.disabled = true;
    up.disabled = true;
    folders.setAttribute("aria-busy", "true");
    folders.replaceChildren();
    selection.textContent = "";
    status.textContent = "LOADING FOLDERS";
    const query = new URLSearchParams({ path, hidden: hidden.checked ? "1" : "0" });
    try {
      const response = await fetch(`/api/markdown/mounts/browse?${query}`);
      const data = await response.json();
      if (token !== requestNumber || !dialog.open) return;
      if (!data.ok) throw new Error(data.error || "Could not browse folder");
      listing = data;
      pathInput.value = data.display_path;
      up.disabled = data.parent === data.path;
      selectFolder(data.path, data.path.split("/").filter(Boolean).pop() || data.path, null, data.display_path);
      data.folders.forEach((folder) => {
        const row = document.createElement("div");
        row.className = "markdown-mount-folder-row";
        const choose = document.createElement("button");
        choose.type = "button";
        choose.className = "markdown-mount-folder-choice";
        choose.textContent = folder.name;
        choose.setAttribute("aria-pressed", "false");
        choose.addEventListener("click", () => selectFolder(folder.path, folder.name, choose, folder.display_path));
        choose.addEventListener("dblclick", () => browse(folder.path));
        const enter = document.createElement("button");
        enter.type = "button";
        enter.className = "markdown-mount-folder-enter";
        enter.textContent = "\u2192";
        enter.title = `Open folder: ${folder.name}`;
        enter.setAttribute("aria-label", enter.title);
        enter.addEventListener("click", () => browse(folder.path));
        row.append(choose, enter);
        folders.append(row);
      });
      if (!data.folders.length) {
        const empty = document.createElement("div");
        empty.className = "subtle markdown-mount-empty";
        empty.textContent = "NO SUBFOLDERS";
        folders.append(empty);
      }
      status.textContent = "";
    } catch (error) {
      if (token === requestNumber && dialog.open) status.textContent = error.message;
    } finally {
      if (token === requestNumber) folders.setAttribute("aria-busy", "false");
    }
  }

  openButton.addEventListener("click", () => {
    dialog.showModal();
    browse();
  });
  cancel.addEventListener("click", () => dialog.close());
  dialog.addEventListener("cancel", (event) => { if (mounting) event.preventDefault(); });
  dialog.addEventListener("close", () => { requestNumber += 1; openButton.focus(); });
  dialog.addEventListener("click", (event) => {
    const rect = dialog.getBoundingClientRect();
    if (!mounting && event.target === dialog &&
        (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom)) {
      dialog.close();
    }
  });
  document.getElementById("markdown-mount-home").addEventListener("click", () => browse());
  up.addEventListener("click", () => { if (listing) browse(listing.parent); });
  hidden.addEventListener("change", () => browse(listing?.path || ""));
  document.getElementById("markdown-mount-path-form").addEventListener("submit", (event) => {
    event.preventDefault();
    browse(pathInput.value.trim());
  });

  confirm.addEventListener("click", async () => {
    if (!selectedPath || mounting) return;
    mounting = true;
    confirm.disabled = true;
    cancel.disabled = true;
    status.textContent = "MOUNTING FOLDER";
    try {
      const response = await fetch("/api/markdown/mounts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: selectedPath, label: nameInput.value.trim() })
      });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "Could not mount folder");
      window.location.href = data.url;
    } catch (error) {
      status.textContent = error.message;
      confirm.disabled = false;
      cancel.disabled = false;
      mounting = false;
    }
  });

  document.querySelectorAll("[data-unmount-root]").forEach((button) => {
    button.addEventListener("click", async () => {
      const root = button.dataset.unmountRoot;
      if (!window.confirm(`Unmount folder "${button.dataset.rootLabel}"?\n${button.dataset.rootPath}\n\nFiles will remain in this folder.`)) return;
      button.disabled = true;
      try {
        const response = await fetch(`/api/markdown/mounts/${encodeURIComponent(root)}/unmount`, { method: "POST" });
        const data = await response.json();
        if (!data.ok) throw new Error(data.error || "Could not unmount folder");
        const context = window.lcarsMarkdown;
        localStorage.removeItem(`${context.libraryKey}:${root}`);
        const saved = new URL(localStorage.getItem(context.libraryKey) || "/markdown", window.location.origin);
        if (saved.searchParams.get("root") === root) localStorage.removeItem(context.libraryKey);
        if (context.root === root) window.location.href = data.url;
        else window.location.reload();
      } catch (error) {
        alert(error.message);
        button.disabled = false;
      }
    });
  });
})();
