(function () {
  const printButton = document.getElementById("print-markdown");
  const surface = document.getElementById("markdown-surface");
  const body = document.getElementById("markdown-body");

  const whiteButton = document.getElementById("md-theme-white");
  const paperButton = document.getElementById("md-theme-paper");
  const darkButton = document.getElementById("md-theme-dark");

  const fontMinus = document.getElementById("md-font-minus");
  const fontReset = document.getElementById("md-font-reset");
  const fontPlus = document.getElementById("md-font-plus");
  const fontFamilyButtons = Array.from(document.querySelectorAll("[data-md-font-family]"));

  const themeKey = "lcars-markdown-theme";
  const fontKey = `markdown-font-scale:${window.location.pathname}`;
  const fontFamilyKey = `markdown-font-family:${window.location.pathname}`;
  const fontFamilies = {
    system: 'Inter, ui-sans-serif, system-ui, sans-serif',
    serif: 'Georgia, "Times New Roman", serif',
    book: '"Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif',
    mono: 'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace'
  };

  let fontScale = Number(localStorage.getItem(fontKey) || 100);
  let fontFamily = localStorage.getItem(fontFamilyKey) || "system";
  let mermaidRenderToken = 0;

  function encodeDocPath(docId) {
    return String(docId || "")
      .split("/")
      .map((part) => encodeURIComponent(part))
      .join("/");
  }

  function getActiveTheme() {
    if (surface && surface.classList.contains("markdown-theme-dark")) return "dark";
    if (surface && surface.classList.contains("markdown-theme-white")) return "white";
    return "paper";
  }

  function getMermaidThemeVariables() {
    const theme = getActiveTheme();

    if (theme === "dark") {
      return {
        background: "#10141f",
        primaryColor: "#79b8ff",
        primaryTextColor: "#111111",
        primaryBorderColor: "#b6dcff",
        secondaryColor: "#e6c36a",
        secondaryTextColor: "#111111",
        secondaryBorderColor: "#ffcf8a",
        tertiaryColor: "#d783c7",
        tertiaryTextColor: "#111111",
        tertiaryBorderColor: "#ffc2ef",
        mainBkg: "#79b8ff",
        secondBkg: "#e6c36a",
        tertiaryBkg: "#d783c7",
        lineColor: "#79b8ff",
        textColor: "#ddd6c7",
        titleColor: "#f7d9b6",
        nodeTextColor: "#111111",
        edgeLabelBackground: "#17181d",
        clusterBkg: "#151d2d",
        clusterBorder: "#79b8ff",
        noteBkgColor: "#17181d",
        noteTextColor: "#ddd6c7",
        noteBorderColor: "#e6c36a"
      };
    }

    if (theme === "white") {
      return {
        background: "#f6f8fa",
        primaryColor: "#79b8ff",
        primaryTextColor: "#111111",
        primaryBorderColor: "#1f6feb",
        secondaryColor: "#e6c36a",
        secondaryTextColor: "#111111",
        secondaryBorderColor: "#9b5a16",
        tertiaryColor: "#d783c7",
        tertiaryTextColor: "#111111",
        tertiaryBorderColor: "#9f4a91",
        mainBkg: "#79b8ff",
        secondBkg: "#e6c36a",
        tertiaryBkg: "#d783c7",
        lineColor: "#1f6feb",
        textColor: "#24292f",
        titleColor: "#1f2328",
        nodeTextColor: "#111111",
        edgeLabelBackground: "#ffffff",
        clusterBkg: "#eef3f8",
        clusterBorder: "#1f6feb",
        noteBkgColor: "#fff6d8",
        noteTextColor: "#24292f",
        noteBorderColor: "#1f6feb"
      };
    }

    return {
      background: "#fbf2dc",
      primaryColor: "#79b8ff",
      primaryTextColor: "#111111",
      primaryBorderColor: "#366c9e",
      secondaryColor: "#e6c36a",
      secondaryTextColor: "#111111",
      secondaryBorderColor: "#8b4f16",
      tertiaryColor: "#d783c7",
      tertiaryTextColor: "#111111",
      tertiaryBorderColor: "#8a477d",
      mainBkg: "#79b8ff",
      secondBkg: "#e6c36a",
      tertiaryBkg: "#d783c7",
      lineColor: "#366c9e",
      textColor: "#2e2418",
      titleColor: "#2e2418",
      nodeTextColor: "#111111",
      edgeLabelBackground: "#fbf2dc",
      clusterBkg: "#efe4c9",
      clusterBorder: "#366c9e",
      noteBkgColor: "#fff3c4",
      noteTextColor: "#2e2418",
      noteBorderColor: "#366c9e"
    };
  }

  function getMermaidBlocks() {
    if (!body) return [];
    return Array.from(body.querySelectorAll(".mermaid"));
  }

  function prepareMermaidBlocks(blocks) {
    blocks.forEach((block) => {
      if (!block.dataset.diagramSource) {
        block.dataset.diagramSource = block.textContent || "";
      }
      block.classList.remove("mermaid-error", "mermaid-unavailable");
      block.removeAttribute("data-processed");
      block.textContent = block.dataset.diagramSource;
    });
  }

  function markMermaidBlocks(blocks, className) {
    blocks.forEach((block) => {
      block.classList.add(className);
      if (block.dataset.diagramSource) {
        block.removeAttribute("data-processed");
        block.textContent = block.dataset.diagramSource;
      }
    });
  }

  function renderMermaidDiagrams() {
    const blocks = getMermaidBlocks();
    if (!blocks.length) return;

    if (!window.mermaid) {
      markMermaidBlocks(blocks, "mermaid-unavailable");
      return;
    }

    const renderToken = ++mermaidRenderToken;
    prepareMermaidBlocks(blocks);

    try {
      window.mermaid.initialize({
        startOnLoad: false,
        securityLevel: "strict",
        theme: "base",
        themeVariables: getMermaidThemeVariables(),
        fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
      });

      const result = window.mermaid.run({ nodes: blocks });
      if (result && typeof result.catch === "function") {
        result.catch((error) => {
          if (renderToken !== mermaidRenderToken) return;
          console.warn("Mermaid render failed", error);
          markMermaidBlocks(blocks, "mermaid-error");
        });
      }
    } catch (error) {
      console.warn("Mermaid render failed", error);
      markMermaidBlocks(blocks, "mermaid-error");
    }
  }

  function applyTheme(theme) {
    if (!surface) return;
    surface.classList.toggle("markdown-theme-white", theme === "white");
    surface.classList.toggle("markdown-theme-paper", theme === "paper");
    surface.classList.toggle("markdown-theme-dark", theme === "dark");
    localStorage.setItem(themeKey, theme);
    renderMermaidDiagrams();
  }

  function applyFontScale() {
    if (!body) return;
    fontScale = Math.max(75, Math.min(140, fontScale));
    body.style.setProperty("--md-scale", String(fontScale / 100));
    localStorage.setItem(fontKey, String(fontScale));
  }

  function applyFontFamily() {
    if (!body) return;
    if (!fontFamilies[fontFamily]) fontFamily = "system";
    body.style.setProperty("--md-font-family", fontFamilies[fontFamily]);
    body.dataset.fontFamily = fontFamily;
    fontFamilyButtons.forEach((button) => {
      button.classList.toggle("active", button.dataset.mdFontFamily === fontFamily);
    });
    localStorage.setItem(fontFamilyKey, fontFamily);
  }

  function installCodeCopyButtons() {
    document.querySelectorAll(".markdown-body pre").forEach((pre) => {
      if (pre.querySelector(".copy-code-button")) return;

      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "COPY";
      button.className = "copy-code-button";

      button.addEventListener("click", async () => {
        const code = pre.querySelector("code");
        const text = code ? code.innerText : pre.innerText.replace(/^COPY\s*/, "");

        try {
          await navigator.clipboard.writeText(text);
          button.textContent = "COPIED";
          setTimeout(() => { button.textContent = "COPY"; }, 1000);
        } catch {
          window.prompt("Copy code:", text);
        }
      });

      pre.classList.add("code-copy-wrapper");
      pre.prepend(button);
    });
  }

  if (printButton) printButton.addEventListener("click", () => window.print());

  if (whiteButton) whiteButton.addEventListener("click", () => applyTheme("white"));
  if (paperButton) paperButton.addEventListener("click", () => applyTheme("paper"));
  if (darkButton) darkButton.addEventListener("click", () => applyTheme("dark"));

  if (fontMinus) {
    fontMinus.addEventListener("click", () => {
      fontScale -= 5;
      applyFontScale();
    });
  }

  if (fontReset) {
    fontReset.addEventListener("click", () => {
      fontScale = 100;
      applyFontScale();
    });
  }

  if (fontPlus) {
    fontPlus.addEventListener("click", () => {
      fontScale += 5;
      applyFontScale();
    });
  }

  fontFamilyButtons.forEach((button) => {
    button.addEventListener("click", () => {
      fontFamily = button.dataset.mdFontFamily || "system";
      applyFontFamily();
    });
  });

  applyTheme(localStorage.getItem(themeKey) || "paper");
  applyFontScale();
  applyFontFamily();
  installCodeCopyButtons();


  const renameButton = document.getElementById("rename-markdown-current");
  if (renameButton) {
    renameButton.addEventListener("click", async () => {
      const docId = renameButton.dataset.docId || "";
      const docName = renameButton.dataset.docName || "";
      const nextName = window.prompt("Rename Markdown file:", docName);
      if (!nextName || !nextName.trim() || nextName.trim() === docName) return;

      renameButton.disabled = true;
      renameButton.textContent = "RENAMING";
      try {
        const response = await fetch(`/api/markdown/rename/${encodeDocPath(docId)}`, {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({ name: nextName.trim() })
        });
        const data = await response.json();
        if (data.ok) {
          window.location.href = data.url || "/markdown";
        } else {
          alert(data.error || "Rename failed");
        }
      } catch (error) {
        alert(error.message || "Rename failed");
      } finally {
        renameButton.disabled = false;
        renameButton.textContent = "RENAME";
      }
    });
  }

  const deleteButton = document.getElementById("delete-markdown-current");
  if (deleteButton) {
    deleteButton.addEventListener("click", async () => {
      const docId = deleteButton.dataset.docId || "";
      const docName = deleteButton.dataset.docName || "";
      const ok = window.confirm(`Delete Markdown file "${docName}"? This cannot be undone.`);
      if (!ok) return;

      deleteButton.disabled = true;
      deleteButton.textContent = "DELETING";
      try {
        const response = await fetch(`/api/markdown/delete/${encodeDocPath(docId)}`, { method: "POST" });
        const data = await response.json();
        if (data.ok) {
          window.location.href = "/markdown";
        } else {
          alert(data.error || "Delete failed");
        }
      } catch (error) {
        alert(error.message || "Delete failed");
      } finally {
        deleteButton.disabled = false;
        deleteButton.textContent = "DELETE";
      }
    });
  }
})();
