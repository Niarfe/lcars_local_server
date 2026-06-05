(function () {
  const listEl = document.getElementById("tmux-list");
  const countEl = document.getElementById("tmux-count");
  const refreshButton = document.getElementById("refresh-tmux");

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  async function copyText(text, button) {
    try {
      await navigator.clipboard.writeText(text);
      const old = button.textContent;
      button.textContent = "COPIED";
      setTimeout(() => { button.textContent = old; }, 900);
    } catch {
      window.prompt("Copy attach command:", text);
    }
  }

  function bindButtons() {
    document.querySelectorAll(".copy-attach").forEach((button) => {
      button.addEventListener("click", () => {
        const command = button.dataset.command || "";
        if (command) copyText(command, button);
      });
    });
  }

  function renderSessions(sessions) {
    countEl.textContent = `${sessions.length} FOUND`;

    if (!sessions.length) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">NO TMUX SESSIONS FOUND</div>
          <div class="subtle">Start one with: tmux new -s session_name</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = sessions.map((session) => `
      <div class="server-card tmux-card">
        <div class="server-main">
          <div class="launch-group">
            <button class="lcars-port copy-attach" data-command="${escapeHtml(session.attach_command || "")}">COPY</button>
            <button class="lcars-tab">${escapeHtml(session.status || "UNKNOWN")}</button>
          </div>

          <div class="server-meta">
            <div class="server-name">${escapeHtml(session.name || "UNKNOWN")}</div>
            <div class="server-badges">
              <span class="server-badge local">${escapeHtml(session.windows || "?")} WINDOWS</span>
              <span class="server-badge ${session.status === "ATTACHED" ? "up" : "remote"}">${escapeHtml(session.status || "UNKNOWN")}</span>
            </div>
            <div class="subtle">ATTACH: ${escapeHtml(session.attach_command || "")}</div>
            ${session.created ? `<div class="server-url">CREATED ${escapeHtml(session.created)} · ACTIVITY ${escapeHtml(session.activity || "")}</div>` : ""}
          </div>
        </div>
      </div>
    `).join("");

    bindButtons();
  }

  async function refreshSessions() {
    refreshButton.disabled = true;
    refreshButton.textContent = "REFRESHING";
    try {
      const response = await fetch("/api/tmux/sessions");
      const payload = await response.json();
      renderSessions(payload.sessions || []);
    } catch (error) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">REFRESH FAILED</div>
          <div class="subtle">${escapeHtml(error.message || "Unknown error")}</div>
        </div>
      `;
      countEl.textContent = "ERROR";
    } finally {
      refreshButton.disabled = false;
      refreshButton.textContent = "REFRESH";
    }
  }

  bindButtons();
  if (refreshButton) refreshButton.addEventListener("click", refreshSessions);
})();
