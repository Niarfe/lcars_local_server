(function () {
  const docId = window.__MARKDOWN_DOC_ID__;
  const editor = document.getElementById("markdown-editor");
  const saveButton = document.getElementById("save-doc");
  const pageBreakButton = document.getElementById("insert-page-break");

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

  function insertPageBreak() {
    const marker = "\n\n<!-- pagebreak -->\n\n";
    const start = editor.selectionStart;
    const end = editor.selectionEnd;
    editor.value = `${editor.value.slice(0, start)}${marker}${editor.value.slice(end)}`;
    const cursor = start + marker.length;
    editor.focus();
    editor.setSelectionRange(cursor, cursor);
  }

  if (pageBreakButton) {
    pageBreakButton.addEventListener("click", insertPageBreak);
  }

  saveButton.addEventListener("click", saveDoc);
})();
