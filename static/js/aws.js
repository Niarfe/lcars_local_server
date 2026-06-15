(function () {
  const listEl = document.getElementById("aws-instance-list");
  const refreshBtn = document.getElementById("aws-refresh");
  const messageEl = document.getElementById("aws-message");
  const configPathEl = document.getElementById("aws-config-path");

  if (!listEl) return;

  function escapeHtml(value) {
    return String(value || "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#39;");
  }

  function setMessage(text) {
    if (messageEl) messageEl.textContent = text || "";
  }

  function stateClass(state) {
    const s = String(state || "").toLowerCase();
    if (s === "running") return "status-up";
    if (s === "stopped" || s === "stopping") return "status-down";
    if (s === "pending") return "status-starting";
    return "";
  }

  function renderInstances(instances) {
    if (!instances || !instances.length) {
      listEl.innerHTML = `
        <div class="empty-state">
          <div class="empty-title">NO ENABLED AWS SERVERS</div>
          <div class="subtle">Edit aws_servers.json and set enabled true for the server you want LCARS to control.</div>
        </div>
      `;
      return;
    }

    listEl.innerHTML = instances.map((inst) => {
      const running = inst.state === "RUNNING";
      const stopped = inst.state === "STOPPED";
      const openUrl = inst.jupyter_url || (inst.public_ip ? `http://${inst.public_ip}:8888` : "");
      const error = inst.error ? `<div class="aws-error">${escapeHtml(inst.error)}</div>` : "";
      return `
        <div class="aws-card" data-instance-id="${escapeHtml(inst.instance_id)}">
          <div class="aws-card-main">
            <div>
              <div class="aws-name">${escapeHtml(inst.name)}</div>
              <div class="subtle">${escapeHtml(inst.instance_id)} · ${escapeHtml(inst.region)}</div>
            </div>
            <div class="aws-state ${stateClass(inst.state)}">${escapeHtml(inst.state)}</div>
          </div>

          <div class="aws-grid">
            <div><span class="label">PUBLIC IP</span><div class="mono">${escapeHtml(inst.public_ip || "-")}</div></div>
            <div><span class="label">PRIVATE IP</span><div class="mono">${escapeHtml(inst.private_ip || "-")}</div></div>
            <div><span class="label">LAUNCH</span><div class="mono">${escapeHtml(inst.launch_time || "-")}</div></div>
          </div>

          ${error}

          <div class="action-list aws-actions">
            <button class="action aws-start" ${running ? "disabled" : ""} data-instance-id="${escapeHtml(inst.instance_id)}" type="button">START</button>
            <button class="action alt aws-stop" ${stopped ? "disabled" : ""} data-instance-id="${escapeHtml(inst.instance_id)}" type="button">STOP</button>
            <a class="action blue ${openUrl ? "" : "disabled-link"}" href="${escapeHtml(openUrl || "#")}" target="_blank" rel="noopener noreferrer">OPEN JUPYTER</a>
          </div>

          ${inst.ssh_hint ? `<div class="mono ssh-hint">${escapeHtml(inst.ssh_hint)}</div>` : ""}
          ${inst.notes ? `<div class="subtle">${escapeHtml(inst.notes)}</div>` : ""}
        </div>
      `;
    }).join("");

    listEl.querySelectorAll(".aws-start").forEach((btn) => {
      btn.addEventListener("click", () => awsAction(btn.dataset.instanceId, "start"));
    });
    listEl.querySelectorAll(".aws-stop").forEach((btn) => {
      btn.addEventListener("click", () => awsAction(btn.dataset.instanceId, "stop"));
    });
  }

  async function loadInstances() {
    setMessage("Checking AWS instance status...");
    try {
      const response = await fetch("/api/aws/instances");
      const data = await response.json();
      if (configPathEl && data.config_path) configPathEl.textContent = data.config_path;
      if (!data.boto3_available) {
        setMessage("boto3 is not installed. Run: pip install boto3");
      } else {
        setMessage("");
      }
      renderInstances(data.instances || []);
    } catch (error) {
      setMessage(error.message || "AWS status failed");
    }
  }

  async function awsAction(instanceId, action) {
    const label = action === "start" ? "START" : "STOP";
    const ok = window.confirm(`${label} AWS instance ${instanceId}?`);
    if (!ok) return;

    setMessage(`${label} request sent...`);
    try {
      const response = await fetch(`/api/aws/instances/${encodeURIComponent(instanceId)}/${action}`, { method: "POST" });
      const data = await response.json();
      setMessage(data.message || `${label} request complete`);
      setTimeout(loadInstances, 1200);
      setTimeout(loadInstances, 5000);
    } catch (error) {
      setMessage(error.message || `${label} failed`);
    }
  }

  if (refreshBtn) refreshBtn.addEventListener("click", loadInstances);
  loadInstances();
})();
