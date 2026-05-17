const mockItems = [
  { id: "doc-101", name: "Brand voice guidelines", type: "Document", status: "indexed" },
  { id: "vid-225", name: "Product walkthrough", type: "Video", status: "processing" },
];

export function AdminMaterialList() {
  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-5">
      <h2 className="mb-4 text-lg">Материалы</h2>
      <div className="grid gap-3">
        {mockItems.map((item) => (
          <div key={item.id} className="rounded border border-[var(--color-border)] p-3">
            <div className="flex items-center justify-between">
              <p>{item.name}</p>
              <span className="mono text-xs text-[var(--color-ash-gray)]">{item.id}</span>
            </div>
            <p className="mt-1 text-sm text-[var(--color-ash-gray)]">
              {item.type} · {item.status}
            </p>
          </div>
        ))}
      </div>
    </section>
  );
}
