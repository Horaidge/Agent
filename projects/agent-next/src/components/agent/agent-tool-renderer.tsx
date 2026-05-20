import type { AgentToolItem } from "@/components/agent/types";

type AgentToolRendererProps = {
  items: AgentToolItem[];
};

export function AgentToolRenderer({ items }: AgentToolRendererProps) {
  return (
    <div className="flex flex-col gap-2 rounded-[var(--radius-default)] border border-[var(--color-border)] bg-[var(--color-deep-space)] p-3">
      <p className="mono text-[10px] uppercase tracking-[0.18em] text-[var(--color-ash-gray)]">
        Tool timeline
      </p>
      <div className="flex flex-col gap-2">
        {items.length === 0 ? (
          <p className="text-sm text-[var(--color-ash-gray)]">Пока нет tool-вызовов в этой сессии.</p>
        ) : (
          items.map((item) => (
            <div key={item.id} className="rounded border border-[var(--color-border)] bg-black/20 p-2">
              <div className="flex items-center justify-between text-xs">
                <span className="mono uppercase tracking-[0.12em] text-[var(--color-ash-gray)]">
                  {item.name}
                </span>
                <span className="mono text-[10px] uppercase tracking-[0.12em] text-[var(--color-amber-glow)]">
                  {item.status}
                </span>
              </div>
              <p className="mt-1 text-sm text-[var(--color-polar-white)]">{item.summary}</p>
              {item.rawPayload ? (
                <details className="mt-2">
                  <summary className="mono cursor-pointer text-[10px] uppercase tracking-[0.12em] text-[var(--color-ash-gray)]">
                    raw payload
                  </summary>
                  <pre className="mt-1 overflow-auto rounded bg-black/30 p-2 text-xs leading-5 text-[var(--color-polar-white)]">
                    {item.rawPayload}
                  </pre>
                </details>
              ) : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
