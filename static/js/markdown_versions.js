(function () {
  const context = window.lcarsMarkdown;
  const repoId = document.body.dataset.versionRepo;
  const editorPrefix = `lcars-version-editor:${repoId}:`;
  const changedKey = `lcars-version-changed:${repoId}`;
  let savedEditor = () => {};

  function dirtyEditors() {
    const dirty = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (!key?.startsWith(editorPrefix)) continue;
      try {
        const item = JSON.parse(localStorage.getItem(key));
        if (Date.now() - item.time < 90000) dirty.push(item.doc);
      } catch { /* Ignore an expired or invalid editor record. */ }
    }
    return dirty;
  }

  function trackEditor(editor, doc) {
    const initial = editor.value;
    const id = crypto.randomUUID().replaceAll("-", "");
    let saved = false;
    let lastDirty = false;
    let lastSent = 0;
    let sequence = 0;
    const dirty = () => !saved && editor.value !== initial;
    function publish(closing = false) {
      const isDirty = !closing && dirty();
      if (repoId) {
        if (isDirty) localStorage.setItem(editorPrefix + id, JSON.stringify({ doc, time: Date.now() }));
        else localStorage.removeItem(editorPrefix + id);
        if (closing || isDirty !== lastDirty || Date.now() - lastSent > 10000) {
          const body = JSON.stringify({ id, doc, dirty: isDirty, sequence: ++sequence });
          const url = context.url("/api/markdown/version/editor");
          if (closing) navigator.sendBeacon(url, new Blob([body], { type: "application/json" }));
          else fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body }).catch(() => {});
          lastSent = Date.now();
        }
      }
      lastDirty = isDirty;
    }
    editor.addEventListener("input", () => publish());
    document.addEventListener("click", () => queueMicrotask(() => publish()));
    let timer = setInterval(() => publish(), 2000);
    window.addEventListener("beforeunload", (event) => {
      if (!dirty()) return;
      event.preventDefault();
      event.returnValue = "";
    });
    window.addEventListener("pagehide", () => { publish(true); clearInterval(timer); });
    window.addEventListener("pageshow", (event) => {
      if (event.persisted) timer = setInterval(() => publish(), 2000);
      publish();
    });
    savedEditor = () => { saved = true; publish(true); };
  }
  window.lcarsVersions = { trackEditor, editorSaved: () => savedEditor() };

  document.addEventListener("DOMContentLoaded", () => {
    const dialog = document.getElementById("version-dialog");
    if (!dialog) return;
    const form = document.getElementById("version-form");
    const title = document.getElementById("version-title");
    const scope = document.getElementById("version-scope");
    const explanation = document.getElementById("version-explanation");
    const status = document.getElementById("version-status");
    const confirm = document.getElementById("version-confirm");
    const close = document.getElementById("version-close");
    const name = document.getElementById("version-name");
    const description = document.getElementById("version-description");
    const tags = document.getElementById("version-tag");
    const remote = document.getElementById("version-remote");
    const pushTag = document.getElementById("version-push-tag");
    const backup = document.getElementById("version-backup");
    const changes = document.getElementById("version-changes");
    const commitFirst = document.getElementById("version-commit-first");
    const feedback = document.getElementById("version-feedback");
    let preview;
    let action;
    let path;
    let busy = false;
    let completed = false;
    let previewRequest = 0;

    const menuButton = document.getElementById("markdown-version-menu");
    const menu = menuButton?.parentElement.querySelector(".actions-menu");
    if (menu) {
      new MutationObserver(() => menuButton.setAttribute("aria-expanded", String(menu.classList.contains("open"))))
        .observe(menu, { attributes: true, attributeFilter: ["class"] });
      menuButton.parentElement.addEventListener("keydown", (event) => {
        const buttons = Array.from(menu.querySelectorAll("button"));
        if (event.key === "Escape") {
          event.preventDefault();
          menu.classList.remove("open");
          menuButton.focus();
        } else if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
          event.preventDefault();
          menu.classList.add("open");
          const index = buttons.indexOf(document.activeElement);
          const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1 :
            index === -1 ? (event.key === "ArrowDown" ? 0 : buttons.length - 1) :
            (index + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
          buttons[next]?.focus();
        }
      });
    }

    function show(id, visible) { document.getElementById(id).classList.toggle("hidden", !visible); }
    function options(select, items, selected = "") {
      select.replaceChildren(...items.map((item) => {
        const option = document.createElement("option");
        option.value = item.value;
        option.textContent = item.text;
        option.selected = item.value === selected;
        return option;
      }));
    }
    function renderChanges(items) {
      changes.replaceChildren();
      changes.classList.toggle("hidden", !items.length);
      for (const item of items) {
        const row = document.createElement("div");
        const code = document.createElement("code");
        const text = document.createElement("span");
        code.textContent = item.status;
        text.textContent = item.original ? `${item.original} → ${item.path}` : item.path;
        row.append(code, text);
        changes.append(row);
      }
    }
    function tagDescription() {
      const tag = preview?.tags.find((item) => item.name === tags.value);
      document.getElementById("version-tag-description").textContent = tag ? `${tag.date}\n${tag.description}` : "";
    }
    function remoteDescription() {
      const selected = preview?.remotes.find((item) => item.name === remote.value);
      const branch = preview?.branch || preview?.return_branch || "";
      const destination = remote.value === preview?.remote ? preview.destination : branch;
      document.getElementById("version-remote-description").textContent = selected ? `${selected.urls.join("\n")}\nBranch: ${branch} → ${destination}. Includes committed repository history.` : "No backup remote is configured. You can still save commits and milestones locally.";
    }
    async function getPreview() {
      const response = await fetch(context.url("/api/markdown/version"), { cache: "no-store" });
      const data = await response.json();
      if (!data.ok) throw new Error(data.error || "Could not read repository status.");
      return data.version;
    }
    async function send(which, payload) {
      const response = await fetch(context.url(`/api/markdown/version/${which}`), {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload)
      });
      const data = await response.json();
      if (!data.ok) {
        const prefix = data.result?.commit ? `Commit ${data.result.commit.slice(0, 12)} was saved locally. ` : "";
        throw new Error(prefix + (data.error || "Version action failed."));
      }
      return data.result;
    }
    function checkEditors() {
      const dirty = dirtyEditors();
      if (dirty.length) throw new Error(`Save or close unsaved LCARS editors first: ${[...new Set(dirty)].join(", ")}`);
    }
    async function open(which, file = "") {
      if (busy) return;
      const requestId = ++previewRequest;
      action = which;
      path = file;
      completed = false;
      preview = null;
      form.reset();
      form.querySelectorAll("input, textarea, select").forEach((field) => { field.disabled = false; });
      for (const field of document.querySelectorAll(".version-fields > *")) field.classList.add("hidden");
      changes.classList.add("hidden");
      commitFirst.classList.add("hidden");
      confirm.disabled = true;
      close.textContent = "CANCEL";
      status.textContent = "Reading repository status…";
      scope.textContent = "";
      explanation.textContent = "";
      title.textContent = { commit: file ? "COMMIT DOCUMENT" : "COMMIT CHANGES", tag: "CREATE MILESTONE TAG", switch: "VIEW AT TAG", latest: "LATEST TAG", return: "RETURN TO CURRENT WORK", push: "PUSH BACKUP" }[which];
      confirm.textContent = { commit: "COMMIT", tag: "SAVE MILESTONE", switch: "VIEW TAG", latest: "VIEW LATEST TAG", return: "RETURN TO CURRENT WORK", push: "PUSH BACKUP" }[which];
      if (!dialog.open) dialog.showModal();
      try {
        const current = await getPreview();
        if (!dialog.open || requestId !== previewRequest) return;
        preview = current;
        scope.textContent = `${preview.repo}\n${preview.branch ? `Working branch: ${preview.branch}` : `Viewing: ${preview.view_tag || "historical commit"}`} · ${preview.head.slice(0, 12) || "no commits yet"}`;
        const switching = ["switch", "latest", "return"].includes(action);
        explanation.textContent = {
          commit: path ? `Commit changes to ${path}. Other unstaged files stay as they are.` : "Review and commit changes across this entire repository, including code and other documents.",
          tag: "This milestone includes all tracked files in this repository. Reviewed changes will be committed before creating an annotated tag.",
          switch: "Switch the entire repository to a saved milestone. Code and documents change together. LCARS editing will be disabled.",
          latest: "Visit the newest tag by creation date that is reachable from your working branch. Your working branch can contain newer commits.",
          return: `Return the entire repository to working branch ${preview.return_branch || "(unavailable)"}, including commits after its latest milestone.`,
          push: "Back up the committed working branch and, optionally, one tag. Uncommitted changes remain local. A rejected push leaves your local commits and tags intact."
        }[action];
        renderChanges(path ? preview.changes.filter((item) => item.path === path || item.original === path) : preview.changes);
        show("version-description-field", action === "commit" || action === "tag");
        show("version-name-field", action === "tag");
        name.required = action === "tag";
        description.required = action === "commit" || action === "tag";
        if (action === "switch" || action === "latest") {
          show("version-tag-field", true);
          show("version-tag-description", true);
          options(tags, preview.tags.map((tag) => ({ value: tag.name, text: `${tag.name} · ${tag.date.slice(0, 10)}` })), action === "latest" ? preview.latest_tag : preview.view_tag);
          tags.disabled = action === "latest";
          tagDescription();
        }
        if (action === "push" || action === "tag") {
          show("version-remote-description", true);
          options(remote, preview.remotes.map((item) => ({ value: item.name, text: item.name })), preview.remote);
          if (!preview.remote) remote.selectedIndex = -1;
          show("version-remote-field", action === "push" || preview.remotes.length > 0);
          show("version-backup-field", action === "tag" && preview.remotes.length > 0);
          options(pushTag, [{ value: "", text: "Branch only" }, ...preview.tags.map((tag) => ({ value: tag.name, text: tag.name }))]);
          show("version-push-tag-field", action === "push");
          remoteDescription();
        }
        let blocked = preview.blocked_reason;
        if (switching) blocked = preview.switch_blocked_reason || blocked;
        if (switching && !preview.clean) {
          blocked = preview.read_only ? "Uncommitted files block switching. Preserve those changes using Git outside LCARS first." : "Commit all changes before switching versions.";
          show("version-commit-first", !preview.read_only);
        }
        if (["commit", "tag", "push"].includes(action) && preview.read_only) blocked = "Return to current work before saving or pushing changes.";
        if (action === "commit" && !(path ? preview.changes.some((item) => item.path === path) : preview.changes.length)) blocked = "There are no changes to commit.";
        if ((action === "switch" && !preview.tags.length) || (action === "latest" && !preview.latest_tag)) blocked = "No saved tag is available for this selection.";
        if (action === "return" && !preview.return_branch) blocked = "No saved working branch is available.";
        if (action === "push" && !preview.remotes.length) blocked = "Configure a backup remote using Git first.";
        try { checkEditors(); } catch (error) { blocked = error.message; }
        status.textContent = blocked || (preview.clean ? "Working copy is clean. Ignored, untracked files are outside milestones." : `${preview.changes.length} changed file(s) in the repository. Git ignore rules apply to new files.`);
        confirm.disabled = Boolean(blocked);
        if (!blocked) (action === "tag" ? name : action === "commit" ? description : confirm).focus();
      } catch (error) {
        if (requestId === previewRequest && dialog.open) status.textContent = error.message;
      }
    }

    document.querySelectorAll("[data-version-action]").forEach((button) => {
      button.addEventListener("click", () => {
        document.querySelectorAll(".actions-menu.open").forEach((menu) => menu.classList.remove("open"));
        open(button.dataset.versionAction, button.dataset.versionPath || "");
      });
    });
    tags.addEventListener("change", tagDescription);
    remote.addEventListener("change", remoteDescription);
    close.addEventListener("click", () => { if (!busy) dialog.close(); });
    dialog.addEventListener("cancel", (event) => { if (busy) event.preventDefault(); });
    commitFirst.addEventListener("click", () => open("commit"));
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (busy || completed || !preview) return;
      if ((action === "push" || (action === "tag" && backup.checked)) && !remote.value) {
        status.textContent = "Choose a backup remote first.";
        return;
      }
      try { checkEditors(); } catch (error) { status.textContent = error.message; return; }
      busy = true;
      const shouldBackup = action === "tag" && backup.checked;
      const selectedRemote = remote.value;
      form.querySelectorAll("input, textarea, select").forEach((field) => { field.disabled = true; });
      confirm.disabled = true;
      close.disabled = true;
      commitFirst.disabled = true;
      status.textContent = "Working…";
      try {
        const result = await send(action, { token: preview.token, name: action === "tag" ? name.value.trim() : tags.value, description: description.value.trim(), path, remote: remote.value, tag: pushTag.value });
        let message = result.message;
        completed = true;
        if (shouldBackup) {
          try {
            const current = await getPreview();
            const pushed = await send("push", { token: current.token, remote: selectedRemote, tag: result.tag });
            message += ` ${pushed.message}`;
          } catch (error) { message += ` Backup failed: ${error.message} Your milestone is saved locally; retry with PUSH BACKUP.`; }
        }
        status.textContent = message;
        feedback.textContent = message;
        feedback.classList.remove("hidden");
        close.textContent = "CLOSE";
        if (["switch", "latest", "return"].includes(action)) {
          localStorage.setItem(changedKey, crypto.randomUUID());
          window.location.assign(context.url("/markdown"));
        }
      } catch (error) {
        status.textContent = error.message;
        // A fresh preview is required after any failed or partially completed operation.
        completed = true;
        close.textContent = "CLOSE";
      } finally {
        busy = false;
        close.disabled = false;
        commitFirst.disabled = false;
      }
    });
    window.addEventListener("storage", (event) => {
      if (event.key !== changedKey) return;
      const editor = document.getElementById("markdown-editor");
      if (editor) {
        editor.readOnly = true;
        document.getElementById("save-doc").disabled = true;
        document.querySelectorAll(".markdown-edit-toolbar button, #insert-page-break").forEach((button) => { button.disabled = true; });
        feedback.textContent = "The repository version changed in another tab. Preserve any text in this editor before reloading.";
        feedback.classList.remove("hidden");
      } else window.location.reload();
    });
  });
})();
