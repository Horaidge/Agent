"use client";

import { useState } from "react";
import { StatusPill } from "@/components/ui/status-pill";

export function AdminUploadForm() {
  const [videoDescription, setVideoDescription] = useState("");

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-5">
      <h2 className="mb-4 text-lg">Управление контентом (mock)</h2>
      <div className="grid gap-4">
        <label className="grid gap-2 text-sm">
          Upload document
          <input
            type="file"
            className="rounded border border-[var(--color-border)] bg-transparent p-2"
            disabled
          />
        </label>
        <label className="grid gap-2 text-sm">
          Upload video
          <input
            type="file"
            className="rounded border border-[var(--color-border)] bg-transparent p-2"
            disabled
          />
        </label>
        <label className="grid gap-2 text-sm">
          Video description
          <textarea
            value={videoDescription}
            onChange={(event) => setVideoDescription(event.target.value)}
            className="min-h-24 rounded border border-[var(--color-border)] bg-transparent p-2"
            placeholder="Описание видео для индексации"
          />
        </label>
        <div className="flex items-center gap-3">
          <span className="text-sm text-[var(--color-ash-gray)]">Index status:</span>
          <StatusPill tone="positive">READY</StatusPill>
        </div>
      </div>
    </section>
  );
}
