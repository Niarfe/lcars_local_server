(function () {
  const docId = window.__MARKDOWN_DOC_ID__;
  const editor = document.getElementById("markdown-editor");
  const saveButton = document.getElementById("save-doc");
  const pageBreakButton = document.getElementById("insert-page-break");
  const openFolderButton = document.getElementById("open-markdown-folder");
  const blockquoteButton = document.getElementById("toggle-blockquote");
  const moveUpButton = document.getElementById("move-lines-up");
  const moveDownButton = document.getElementById("move-lines-down");

  function encodeDocPath(path) {
    return String(path || "")
      .split("/")
      .map((part) => encodeURIComponent(part))
      .join("/");
  }

  async function saveDoc() {
    saveButton.disabled = true;
    saveButton.textContent = "SAVING";
    try {
      const response = await fetch(`/api/markdown/save/${encodeDocPath(docId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: editor.value })
      });
      const data = await response.json();
      if (data.ok) {
        window.location.href = `/md/view/${encodeDocPath(docId)}`;
      } else {
        alert(data.error || "Save failed");
      }
    } catch (error) {
      alert(error.message || "Save failed");
    } finally {
      saveButton.disabled = false;
      saveButton.textContent = "SAVE";
    }
  }

  async function openMarkdownFolder(button) {
    const currentDocId = button.dataset.docId || docId;
    button.disabled = true;
    const previousText = button.textContent;
    button.textContent = "OPENING";

    try {
      const response = await fetch(`/api/markdown/open-folder/${encodeDocPath(currentDocId)}`, {
        method: "POST"
      });
      const data = await response.json();
      if (!data.ok) {
        alert(data.error || "Could not open folder");
      }
    } catch (error) {
      alert(error.message || "Could not open folder");
    } finally {
      button.disabled = false;
      button.textContent = previousText;
    }
  }

  function insertPageBreak() {
    const marker = "\n\n<!-- pagebreak -->\n\n";
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    editor.value = `${editor.value.slice(0, start)}${marker}${editor.value.slice(end)}`;
    const cursor = start + marker.length;
    editor.focus();
    editor.setSelectionRange(cursor, cursor);
  }

  function selectedLineBlock() {
    const text = editor.value;
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    const previousBreak = start === 0 ? -1 : text.lastIndexOf("\n", start - 1);
    const lineStart = previousBreak + 1;
    const adjustedEnd = end > start && text[end - 1] === "\n" ? end - 1 : end;
    const lineBreakAfter = text.indexOf("\n", adjustedEnd);
    const lineEnd = lineBreakAfter === -1 ? text.length : lineBreakAfter;
    const lineEndWithBreak = lineBreakAfter === -1 ? text.length : lineBreakAfter + 1;

    return {
      lineStart,
      lineEnd,
      lineEndWithBreak,
      text: text.slice(lineStart, lineEnd)
    };
  }

  function replaceLineBlock(block, replacement) {
    editor.value = `${editor.value.slice(0, block.lineStart)}${replacement}${editor.value.slice(block.lineEnd)}`;
    editor.focus();
    editor.setSelectionRange(block.lineStart, block.lineStart + replacement.length);
  }

  function isQuotedLine(line) {
    return /^\s*> ?/.test(line);
  }

  function quoteLine(line) {
    if (isQuotedLine(line)) return line;
    const indent = line.match(/^\s*/)[0];
    return `${indent}> ${line.slice(indent.length)}`;
  }

  function unquoteLine(line) {
    return line.replace(/^(\s*)> ?/, "$1");
  }

  function toggleBlockquote() {
    const block = selectedLineBlock();
    const lines = block.text.split("\n");
    const quotedLines = lines.filter(isQuotedLine);
    const contentLines = lines.filter((line) => line.trim() !== "");
    const shouldUnquote = quotedLines.length > 0 &&
      (contentLines.length === 0 || contentLines.every(isQuotedLine));
    const replacement = lines
      .map((line) => shouldUnquote ? unquoteLine(line) : quoteLine(line))
      .join("\n");

    replaceLineBlock(block, replacement);
  }

  function moveSelectedLines(direction) {
    const block = selectedLineBlock();
    const text = editor.value;

    if (direction < 0) {
      if (block.lineStart === 0) return;

      const previousEnd = block.lineStart - 1;
      const previousStart = text.lastIndexOf("\n", previousEnd - 1) + 1;
      const previousBlock = text.slice(previousStart, block.lineStart);
      const selectedBlock = text.slice(block.lineStart, block.lineEndWithBreak);
      const nextText = `${text.slice(0, previousStart)}${selectedBlock}${previousBlock}${text.slice(block.lineEndWithBreak)}`;

      editor.value = nextText;
      editor.focus();
      editor.setSelectionRange(previousStart, previousStart + block.text.length);
      return;
    }

    if (block.lineEndWithBreak >= text.length) return;

    const nextStart = block.lineEndWithBreak;
    const nextBreak = text.indexOf("\n", nextStart);
    const nextEndWithBreak = nextBreak === -1 ? text.length : nextBreak + 1;
    const nextBlock = text.slice(nextStart, nextEndWithBreak);
    const selectedBlock = text.slice(block.lineStart, block.lineEndWithBreak);
    const nextText = `${text.slice(0, block.lineStart)}${nextBlock}${selectedBlock}${text.slice(nextEndWithBreak)}`;
    const movedStart = block.lineStart + nextBlock.length;

    editor.value = nextText;
    editor.focus();
    editor.setSelectionRange(movedStart, movedStart + block.text.length);
  }

  function handleEditorKeydown(event) {
    const usesCommand = event.metaKey || event.ctrlKey;
    const key = event.key.toLowerCase();

    if (usesCommand && key === "s") {
      event.preventDefault();
      saveDoc();
      return;
    }

    if (usesCommand && event.shiftKey && event.key === ".") {
      event.preventDefault();
      toggleBlockquote();
      return;
    }

    if (event.altKey && !event.metaKey && !event.ctrlKey) {
      if (event.key === "ArrowUp" || event.code === "KeyK") {
        event.preventDefault();
        moveSelectedLines(-1);
      } else if (event.key === "ArrowDown" || event.code === "KeyJ") {
        event.preventDefault();
        moveSelectedLines(1);
      }
    }
  }

  if (pageBreakButton) {
    pageBreakButton.addEventListener("click", insertPageBreak);
  }

  if (openFolderButton) {
    openFolderButton.addEventListener("click", () => openMarkdownFolder(openFolderButton));
  }

  if (blockquoteButton) {
    blockquoteButton.addEventListener("click", toggleBlockquote);
  }

  if (moveUpButton) {
    moveUpButton.addEventListener("click", () => moveSelectedLines(-1));
  }

  if (moveDownButton) {
    moveDownButton.addEventListener("click", () => moveSelectedLines(1));
  }

  editor.addEventListener("keydown", handleEditorKeydown);
  saveButton.addEventListener("click", saveDoc);
})();
