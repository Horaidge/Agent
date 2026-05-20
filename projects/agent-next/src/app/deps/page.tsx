import { promises as fs } from "fs";
import Link from "next/link";
import path from "path";
import { MermaidGraph } from "@/components/deps/mermaid-graph";

async function readReport(fileName: string): Promise<string> {
  try {
    return await fs.readFile(path.join(process.cwd(), "reports", fileName), "utf8");
  } catch {
    return "";
  }
}

function mapPathToLayer(filePath: string): string {
  if (filePath.startsWith("src/components/landing/")) return "components_landing";
  if (filePath.startsWith("src/components/agent/")) return "components_agent";
  if (filePath.startsWith("src/components/admin/")) return "components_admin";
  if (filePath.startsWith("src/components/ui/")) return "components_ui";
  if (filePath.startsWith("src/components/animations/")) return "components_animations";
  if (filePath.startsWith("src/components/")) return "components_other";
  if (filePath.startsWith("src/orchestration/")) return "orchestration";
  if (filePath.startsWith("src/shared/")) return "shared";
  if (filePath.startsWith("src/audio/")) return "audio";
  if (filePath.startsWith("src/app/admin/")) return "app_admin";
  if (filePath.startsWith("src/app/login/")) return "app_login";
  if (filePath.startsWith("src/app/voice/")) return "app_voice";
  if (filePath.startsWith("src/app/")) return "app_site";
  return "other";
}

function layerLabel(layer: string): string {
  const map: Record<string, string> = {
    app_site: "app (site)",
    app_voice: "app (voice)",
    app_admin: "app (admin)",
    app_login: "app (login)",
    components_landing: "components/landing",
    components_agent: "components/agent",
    components_admin: "components/admin",
    components_ui: "components/ui",
    components_animations: "components/animations",
    components_other: "components/*",
    orchestration: "orchestration",
    shared: "shared",
    audio: "audio",
    other: "other",
  };
  return map[layer] ?? layer;
}

function buildLayerMermaid(textGraph: string): string {
  const edges = new Set<string>();
  const layers = new Set<string>();
  const lines = textGraph.split("\n").filter(Boolean);

  for (const line of lines) {
    const arrow = " → ";
    const index = line.indexOf(arrow);
    if (index === -1) continue;
    const fromPath = line.slice(0, index).trim();
    const toPath = line.slice(index + arrow.length).trim();
    const fromLayer = mapPathToLayer(fromPath);
    const toLayer = mapPathToLayer(toPath);
    layers.add(fromLayer);
    layers.add(toLayer);
    if (fromLayer !== toLayer) {
      edges.add(`${fromLayer}-->${toLayer}`);
    }
  }

  const nodes = [...layers]
    .sort()
    .map((layer) => `${layer}["${layerLabel(layer)}"]`)
    .join("\n");
  const links = [...edges].sort().join("\n");

  return `flowchart LR\n${nodes}\n${links}`;
}

export default async function DependencyReportsPage() {
  const textGraph = await readReport("dependency-cruiser-graph.txt");
  const mermaidGraph = await readReport("dependency-cruiser-graph.mmd");
  const layerMermaidGraph = buildLayerMermaid(textGraph);
  const hasGraph = textGraph.length > 0;

  return (
    <main className="min-h-dvh bg-[var(--color-midnight-void)] px-6 py-10 text-[var(--color-polar-white)]">
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-6">
        <header className="flex items-center justify-between gap-3">
          <div>
            <p className="mono text-xs uppercase tracking-[0.16em] text-[var(--color-ash-gray)]">
              dependency cruiser
            </p>
            <h1 className="text-3xl">Architecture links preview</h1>
          </div>
          <Link href="/" className="text-sm text-[var(--color-ash-gray)] hover:text-[var(--color-polar-white)]">
            Back to site
          </Link>
        </header>

        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4">
          <p className="mb-3 text-sm text-[var(--color-ash-gray)]">
            Эта страница показывает текущие отчеты dependency-cruiser из корня проекта. Чтобы
            обновить данные, выполните:
          </p>
          <pre className="mono overflow-x-auto rounded bg-black/20 p-3 text-xs">
            pnpm depcruise{"\n"}
            pnpm depcruise:json{"\n"}
            pnpm depcruise:dot{"\n"}
            pnpm depcruise:text{"\n"}
            pnpm depcruise:mermaid{"\n"}
            pnpm depcruise:html
          </pre>
        </section>

        <section className="grid gap-4 md:grid-cols-2">
          <a
            href="/api/reports/dependency-cruiser-report.html"
            target="_blank"
            rel="noreferrer"
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4 text-sm hover:border-[var(--color-amber-glow)]"
          >
            Open HTML validation report
          </a>
          <a
            href="/api/reports/dependency-cruiser-report.json"
            target="_blank"
            rel="noreferrer"
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4 text-sm hover:border-[var(--color-amber-glow)]"
          >
            Open JSON dependencies report
          </a>
          <a
            href="/api/reports/dependency-cruiser-graph.txt"
            target="_blank"
            rel="noreferrer"
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4 text-sm hover:border-[var(--color-amber-glow)]"
          >
            Open TXT graph list
          </a>
          <a
            href="/api/reports/dependency-cruiser-graph.mmd"
            target="_blank"
            rel="noreferrer"
            className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4 text-sm hover:border-[var(--color-amber-glow)]"
          >
            Open Mermaid graph file
          </a>
        </section>

        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4">
          <h2 className="mb-2 text-xl">Dependency graph (layers)</h2>
          <p className="mb-3 text-sm text-[var(--color-ash-gray)]">
            Упрощенный граф по слоям — здесь обычно сразу видно архитектуру.
          </p>
          <MermaidGraph chart={layerMermaidGraph} />
        </section>

        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4">
          <h2 className="mb-3 text-xl">Dependency graph (visual)</h2>
          <p className="mb-3 text-sm text-[var(--color-ash-gray)]">
            Полный граф по файлам. Он плотный, но полезен для детального разбора.
          </p>
          {mermaidGraph ? (
            <MermaidGraph chart={mermaidGraph} />
          ) : (
            <p className="text-sm text-[var(--color-ash-gray)]">
              dependency-cruiser-graph.mmd еще не создан. Выполните pnpm depcruise:mermaid.
            </p>
          )}
        </section>

        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-4">
          <h2 className="mb-3 text-xl">Quick graph preview</h2>
          {hasGraph ? (
            <pre className="max-h-[32rem] overflow-auto rounded bg-black/20 p-4 text-xs leading-5">
              {textGraph}
            </pre>
          ) : (
            <p className="text-sm text-[var(--color-ash-gray)]">
              dependency-cruiser-graph.txt еще не создан. Запустите команды из блока выше.
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
