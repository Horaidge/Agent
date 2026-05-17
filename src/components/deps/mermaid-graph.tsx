"use client";

import mermaid from "mermaid";
import { useEffect, useId, useState } from "react";

type MermaidGraphProps = {
  chart: string;
};

export function MermaidGraph({ chart }: MermaidGraphProps) {
  const [svg, setSvg] = useState<string>("");
  const [error, setError] = useState<string>("");
  const graphId = `dep-graph-${useId().replace(/[^a-zA-Z0-9_-]/g, "")}`;

  useEffect(() => {
    let cancelled = false;

    async function renderGraph() {
      if (!chart.trim()) {
        setError("Файл графа пуст. Сначала запустите pnpm depcruise:mermaid.");
        return;
      }

      try {
        mermaid.initialize({
          startOnLoad: false,
          theme: "dark",
          securityLevel: "loose",
        });
        const { svg: rendered } = await mermaid.render(graphId, chart);
        if (!cancelled) {
          setSvg(rendered);
          setError("");
        }
      } catch (renderError) {
        if (!cancelled) {
          setSvg("");
          setError(
            renderError instanceof Error
              ? renderError.message
              : "Не удалось отрисовать mermaid-граф.",
          );
        }
      }
    }

    void renderGraph();
    return () => {
      cancelled = true;
    };
  }, [chart, graphId]);

  if (error) {
    return (
      <div className="rounded border border-[var(--color-border)] bg-black/20 p-4 text-sm text-red-300">
        {error}
      </div>
    );
  }

  if (!svg) {
    return (
      <div className="rounded border border-[var(--color-border)] bg-black/20 p-4 text-sm text-[var(--color-ash-gray)]">
        Рендерим граф зависимостей...
      </div>
    );
  }

  return (
    <div
      className="overflow-auto rounded border border-[var(--color-border)] bg-black/20 p-4 [&_svg]:h-auto [&_svg]:min-w-[900px] [&_svg]:max-w-none"
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
