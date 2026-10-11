(function () {
  const printButton = document.getElementById("print-collated-document");
  const shouldAutoPrint = document.body.dataset.autoPrint === "true";

  async function prepareDiagrams() {
    const diagrams = Array.from(document.querySelectorAll(".mermaid"));
    if (!diagrams.length || !window.mermaid) return;

    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "strict",
      theme: "default",
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace"
    });
    await window.mermaid.run({ nodes: diagrams });
  }

  async function printCollatedDocument() {
    try {
      await prepareDiagrams();
      if (document.fonts?.ready) await document.fonts.ready;
    } catch (error) {
      console.warn("Collated diagram rendering failed", error);
    }
    window.print();
  }

  printButton?.addEventListener("click", printCollatedDocument);
  if (shouldAutoPrint) {
    window.addEventListener("load", () => {
      window.setTimeout(printCollatedDocument, 100);
    }, { once: true });
  }
})();
