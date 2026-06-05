(function () {
  const docId = window.__MARKDOWN_DOC_ID__;
  const editor = document.getElementById("markdown-editor");
  const saveButton = document.getElementById("save-doc");

  async function saveDoc() {
    saveButton.disabled = true;
    saveButton.textContent = "SAVING";
    try {
      const response = await fetch(`/api/markdown/save/${encodeURIComponent(docId)}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: editor.value })
      });
      const data = await response.json();
      if (data.ok) {
        window.location.href = `/md/view/${encodeURIComponent(docId)}`;
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

  saveButton.addEventListener("click", saveDoc);
})();
