(function () {
  const phaseEl = document.getElementById("focus-phase");
  const timeEl = document.getElementById("focus-time");
  const sublineEl = document.getElementById("focus-subline");
  const progressEl = document.getElementById("focus-progress");
  const consoleEl = document.querySelector(".focus-console");

  const startBtn = document.getElementById("start-focus");
  const pauseBtn = document.getElementById("pause-focus");
  const resetBtn = document.getElementById("reset-focus");
  const applyBtn = document.getElementById("apply-custom");
  const focusInput = document.getElementById("focus-minutes");
  const breakInput = document.getElementById("break-minutes");

  let focusMinutes = Number(localStorage.getItem("focus-minutes") || 10);
  let breakMinutes = Number(localStorage.getItem("break-minutes") || 3);
  let phase = "focus";
  let state = "stopped"; // stopped | running | paused | done
  let doneReason = "";
  let totalSeconds = focusMinutes * 60;
  let remainingSeconds = totalSeconds;
  let timer = null;

  let focusConfig = {
    work_mode_sound: "",
    break_mode_sound: "",
    work_complete_sound: "",
    break_complete_sound: "",
    use_beep_fallback: true,
    stop_break_sound_on_done: true
  };

  let workAudio = null;
  let breakAudio = null;

  focusInput.value = focusMinutes;
  breakInput.value = breakMinutes;

  function pad(n) { return String(n).padStart(2, "0"); }
  function fmt(seconds) { return `${pad(Math.floor(seconds / 60))}:${pad(seconds % 60)}`; }

  async function loadFocusConfig() {
    try {
      const response = await fetch("/api/focus/config");
      const data = await response.json();
      if (data.ok && data.config) focusConfig = { ...focusConfig, ...data.config };
    } catch {}

    const workPath = focusConfig.work_mode_sound || focusConfig.work_complete_sound || "";
    const breakPath = focusConfig.break_mode_sound || focusConfig.break_complete_sound || "";

    workAudio = workPath ? new Audio(workPath) : null;
    breakAudio = breakPath ? new Audio(breakPath) : null;

    [workAudio, breakAudio].forEach((audio) => {
      if (!audio) return;
      audio.preload = "auto";
      audio.loop = true;
      audio.volume = 0.9;
      audio.load();
    });
  }

  function setConsoleState() {
    consoleEl.classList.toggle("focus-state-work", state === "running" && phase === "focus");
    consoleEl.classList.toggle("focus-state-break", state === "running" && phase === "break");
    consoleEl.classList.toggle("focus-state-paused", state === "paused");
    consoleEl.classList.toggle("focus-state-stopped", state === "stopped");
    consoleEl.classList.toggle("focus-state-done", state === "done");
  }

  function update() {
    let label = "READY";
    if (state === "running") label = phase === "focus" ? "WORK BLOCK" : "BREAK BLOCK";
    if (state === "paused") label = "PAUSED";
    if (state === "done") label = doneReason === "break" ? "CYCLE COMPLETE" : "DONE";

    phaseEl.textContent = label;
    timeEl.textContent = fmt(remainingSeconds);
    sublineEl.textContent =
      state === "done"
        ? "CYCLE COMPLETE · START BEGINS NEW WORK BLOCK"
        : `${focusMinutes} MIN FOCUS · ${breakMinutes} MIN BREAK`;

    const done = totalSeconds ? (1 - remainingSeconds / totalSeconds) * 100 : 0;
    progressEl.style.width = `${Math.max(0, Math.min(100, done))}%`;

    setConsoleState();
    document.title = state === "running" ? `${fmt(remainingSeconds)} · ${label}` : `LCARS Focus · ${label}`;
  }

  function stopAudio(audio) {
    if (!audio) return;
    audio.pause();
    try { audio.currentTime = 0; } catch {}
  }

  function stopAllAudio() {
    stopAudio(workAudio);
    stopAudio(breakAudio);
  }

  function beep(durationMs = 550, frequency = 880) {
    try {
      const AudioContext = window.AudioContext || window.webkitAudioContext;
      const ctx = new AudioContext();
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.type = "sine";
      osc.frequency.value = frequency;
      gain.gain.setValueAtTime(0.001, ctx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.22, ctx.currentTime + 0.03);
      gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + durationMs / 1000);
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      osc.stop(ctx.currentTime + durationMs / 1000 + 0.05);
    } catch {}
  }

  async function playAudio(audio, kind) {
    if (audio) {
      try {
        audio.currentTime = 0;
        await audio.play();
        return;
      } catch {}
    }
    if (focusConfig.use_beep_fallback !== false) {
      beep(kind === "work" ? 650 : 500, kind === "work" ? 880 : 660);
    }
  }

  function pulse() {
    consoleEl.classList.add("focus-pulse");
    setTimeout(() => consoleEl.classList.remove("focus-pulse"), 1500);
  }

  function startWorkCycle() {
    phase = "focus";
    state = "running";
    doneReason = "";
    totalSeconds = focusMinutes * 60;
    remainingSeconds = totalSeconds;
    stopAllAudio();
    playAudio(workAudio, "work");
    if (!timer) timer = setInterval(tick, 1000);
    update();
  }

  function startBreakCycle() {
    phase = "break";
    state = "running";
    doneReason = "";
    totalSeconds = breakMinutes * 60;
    remainingSeconds = totalSeconds;
    stopAudio(workAudio);
    playAudio(breakAudio, "break");
    update();
    pulse();
  }

  function finishBreakCycle() {
    doneReason = "break";
    state = "done";
    remainingSeconds = 0;
    if (focusConfig.stop_break_sound_on_done !== false) stopAudio(breakAudio);
    update();
    pulse();
  }

  function tick() {
    if (state !== "running") return;
    remainingSeconds -= 1;

    if (remainingSeconds <= 0) {
      if (phase === "focus") startBreakCycle();
      else finishBreakCycle();
    } else {
      update();
    }
  }

  function start() {
    startWorkCycle();
  }

  function pause() {
    if (state !== "running") return;
    state = "paused";
    stopAllAudio();
    update();
  }

  function reset() {
    state = "stopped";
    phase = "focus";
    doneReason = "";
    totalSeconds = focusMinutes * 60;
    remainingSeconds = totalSeconds;
    stopAllAudio();
    update();
  }

  function applyCustom() {
    focusMinutes = Math.max(1, Number(focusInput.value || 10));
    breakMinutes = Math.max(1, Number(breakInput.value || 3));
    localStorage.setItem("focus-minutes", String(focusMinutes));
    localStorage.setItem("break-minutes", String(breakMinutes));
    reset();
  }

  document.querySelectorAll(".focus-preset").forEach((button) => {
    button.addEventListener("click", () => {
      focusMinutes = Number(button.dataset.focus);
      breakMinutes = Number(button.dataset.break);
      focusInput.value = focusMinutes;
      breakInput.value = breakMinutes;
      localStorage.setItem("focus-minutes", String(focusMinutes));
      localStorage.setItem("break-minutes", String(breakMinutes));
      reset();
    });
  });

  startBtn.addEventListener("click", start);
  pauseBtn.addEventListener("click", pause);
  resetBtn.addEventListener("click", reset);
  applyBtn.addEventListener("click", applyCustom);

  loadFocusConfig();
  update();
})();