window.mermaidConfig = {
  startOnLoad: false,
  securityLevel: "loose",
  theme: "default",
};

function renderMermaidDiagrams() {
  if (!window.mermaid) return;

  window.mermaid.initialize(window.mermaidConfig);
  window.mermaid.run({
    querySelector: ".mermaid",
  });
}

if (window.document$ && typeof window.document$.subscribe === "function") {
  window.document$.subscribe(renderMermaidDiagrams);
} else {
  document.addEventListener("DOMContentLoaded", renderMermaidDiagrams);
}
