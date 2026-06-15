(function () {
  const initialServers = Array.isArray(window.__INITIAL_JUPYTER_SERVERS__)
    ? window.__INITIAL_JUPYTER_SERVERS__
    : [];

  const serverList = document.getElementById("server-list");
  const serverCount = document.getElementById("server-count");
  const refreshButton = document.getElementById("refresh-button");

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function labelFromServer(server) {
    const explicit = String(server.label || "").trim();
    if (explicit) return explicit.toUpperCase();

    const raw = String(server.root_dir || "").trim();
    if (!raw) return "UNKNOWN";
    const normalized = raw.replace(/\/+$/, "");
    const last = normalized.split("/").filter(Boolean).pop() || "UNKNOWN";
    return last.replaceAll("_", " ").toUpperCase();
  }

  function badgeHtml(server) {
    if (server.is_remote) {
      const statusClass = server.remote_status === "UP" ? "up" : "down";
      const statusText = server.remote_status || "DOWN";
      return `
        <div class="server-badges">
          <span class="server-badge remote">REMOTE</span>
          <span class="server-badge ${statusClass}">${escapeHtml(statusText)}</span>
        </div>
      `;
    }
    return `
      <div class="server-badges">
        <span class="server-badge local">LOCAL</span>
      </div>
    `;
  }

  function bindButtons() {
    document.querySelectorAll(".lcars-port").forEach((button) => {
      button.addEventListener("click", () => {
        const url = button.dataset.url;
        if (url) {
          window.location.href = url;
        }
      });
    });

    document.querySelectorAll(".open-tab").forEach((button) => {
      button.addEventListener("click", () => {
        const url = button.dataset.url;
        if (url) {
          window.open(url, "_blank", "noopener,noreferrer");
        }
      });
    });
  }

  function renderServers(servers) {
    serverCount.textContent = `${servers.length} ACTIVE`;

    if (!servers.length) {
      serverList.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">NO JUPYTER SERVERS FOUND</div>
          <div class="subtle">Start Jupyter Lab or Notebook, then refresh this page.</div>
        </div>
      `;
      return;
    }

    serverList.innerHTML = servers.map((server) => `
      <div class="server-card">
        <div class="server-main">
          <div class="launch-group">
            <button class="lcars-port" data-url="${escapeHtml(server.url || "")}">
              ${escapeHtml(server.port || "----")}
            </button>
            <button class="lcars-tab open-tab" data-url="${escapeHtml(server.url || "")}">
              TAB
            </button>
          </div>

          <div class="server-meta">
            <div class="server-name">${escapeHtml(labelFromServer(server))}</div>
            ${badgeHtml(server)}
            <div class="subtle">PID ${escapeHtml(server.pid || "?")}</div>
            <div class="server-url">${escapeHtml(server.url || "")}</div>
          </div>
        </div>
      </div>
    `).join("");

    bindButtons();
  }

  async function refreshServers() {
    refreshButton.disabled = true;
    refreshButton.textContent = "REFRESHING";
    try {
      const response = await fetch("/api/jupyter/servers");
      const payload = await response.json();
      renderServers(payload.servers || []);
    } catch (error) {
      serverList.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">REFRESH FAILED</div>
          <div class="subtle">${escapeHtml(error.message || "Unknown error")}</div>
        </div>
      `;
      serverCount.textContent = "ERROR";
    } finally {
      refreshButton.disabled = false;
      refreshButton.textContent = "REFRESH";
    }
  }

  renderServers(initialServers);

  if (refreshButton) {
    refreshButton.addEventListener("click", refreshServers);
  }
})();

(function () {
  const statusEl = document.getElementById("lcars-lab-status");
  const rootEl = document.getElementById("lcars-lab-root");
  const tmuxEl = document.getElementById("lcars-lab-tmux");
  const portEl = document.getElementById("lcars-lab-port");
  const msgEl = document.getElementById("lcars-lab-message");
  const startBtn = document.getElementById("lcars-lab-start");
  const openLink = document.getElementById("lcars-lab-open");
  const refreshBtn = document.getElementById("lcars-lab-refresh");

  if (!statusEl) return;

  function setMessage(text) {
    if (msgEl) msgEl.textContent = text;
  }

  function applyStatus(lab) {
    statusEl.textContent = lab.status || "UNKNOWN";
    statusEl.classList.toggle("status-up", lab.status === "UP");
    statusEl.classList.toggle("status-down", lab.status === "DOWN");
    statusEl.classList.toggle("status-starting", lab.status === "STARTING");

    if (rootEl) rootEl.textContent = lab.app_dir || "-";
    if (tmuxEl) tmuxEl.textContent = lab.tmux_running ? lab.session : "DOWN";
    if (portEl) portEl.textContent = lab.server && lab.server.port ? lab.server.port : "-";

    const openUrl = lab.server && lab.server.open_url ? lab.server.open_url : "";
    if (openLink) {
      if (openUrl) {
        openLink.href = openUrl;
        openLink.classList.remove("disabled-link");
      } else {
        openLink.href = "#";
        openLink.classList.add("disabled-link");
      }
    }
  }

  async function refreshLab() {
    try {
      const response = await fetch("/api/lcars-lab/status");
      const data = await response.json();
      if (data.ok) applyStatus(data.lab || {});
    } catch (error) {
      statusEl.textContent = "ERROR";
      setMessage(error.message || "Status check failed");
    }
  }

  async function startLab() {
    if (!startBtn) return;
    startBtn.disabled = true;
    startBtn.textContent = "STARTING";
    setMessage("Starting lcars_lab tmux session...");

    try {
      const response = await fetch("/api/lcars-lab/start", { method: "POST" });
      const data = await response.json();
      setMessage(data.message || (data.ok ? "Started" : "Start failed"));
      if (data.lab) applyStatus(data.lab);
      setTimeout(refreshLab, 2000);
      setTimeout(refreshLab, 5000);
    } catch (error) {
      setMessage(error.message || "Start failed");
    } finally {
      startBtn.disabled = false;
      startBtn.textContent = "START";
    }
  }

  if (startBtn) startBtn.addEventListener("click", startLab);
  if (refreshBtn) refreshBtn.addEventListener("click", refreshLab);
  refreshLab();
})();
