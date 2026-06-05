(function () {
  const titleInput = document.getElementById("new-md-title");
  const createButton = document.getElementById("create-md");
  const errorEl = document.getElementById("new-md-error");

  async function createDoc() {
    const title = titleInput.value.trim();
    if (!title) {
      errorEl.textContent = "TITLE REQUIRED";
      return;
    }

    createButton.disabled = true;
    createButton.textContent = "CREATING";
    errorEl.textContent = "";

    try {
      const response = await fetch("/api/markdown/create", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({ title })
      });
      const data = await response.json();
      if (data.ok) {
        window.location.href = `/md/edit/${encodeURIComponent(data.id)}`;
      } else {
        errorEl.textContent = data.error || "CREATE FAILED";
      }
    } catch (error) {
      errorEl.textContent = error.message || "CREATE FAILED";
    } finally {
      createButton.disabled = false;
      createButton.textContent = "CREATE MARKDOWN FILE";
    }
  }

  createButton.addEventListener("click", createDoc);
  titleInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter") createDoc();
  });
})();
