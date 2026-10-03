window.mermaidConfig = {
  startOnLoad: false,
  securityLevel: "loose",
  theme: "neutral",
};

async function renderMermaidDiagrams() {
  if (!window.mermaid) return;

  // pymdownx.superfences emits <pre class="mermaid"><code>...</code></pre>.
  // Mermaid expects the diagram source directly inside its target element.
  document.querySelectorAll("pre.mermaid").forEach((pre) => {
    const diagram = document.createElement("div");
    diagram.className = "mermaid";
    diagram.textContent = pre.textContent;
    pre.replaceWith(diagram);
  });

  window.mermaidConfig.theme = document.body.getAttribute("data-md-color-scheme") === "slate" ? "dark" : "neutral";
  window.mermaid.initialize(window.mermaidConfig);
  await window.mermaid.run({ querySelector: ".mermaid" });
}

if (window.document$ && typeof window.document$.subscribe === "function") {
  window.document$.subscribe(renderMermaidDiagrams);
} else {
  document.addEventListener("DOMContentLoaded", renderMermaidDiagrams);
}
