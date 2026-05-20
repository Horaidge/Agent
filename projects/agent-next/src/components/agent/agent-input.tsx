"use client";

import { useState } from "react";

type AgentInputProps = {
  onSend: (message: string) => void;
};

export function AgentInput({ onSend }: AgentInputProps) {
  const [draft, setDraft] = useState("");

  return (
    <form
      className="flex min-w-0 gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        const value = draft.trim();
        if (!value) return;
        onSend(value);
        setDraft("");
      }}
    >
      <input
        value={draft}
        onChange={(event) => setDraft(event.target.value)}
        placeholder="Напишите сообщение..."
        className="min-h-12 min-w-0 flex-1 rounded-xl border border-[var(--color-border)] bg-[linear-gradient(90deg,rgba(255,255,255,0.05),rgba(20,21,28,0.9))] px-4 text-sm outline-none transition-all placeholder:text-[var(--color-ash-gray)] focus:border-[var(--color-amber-glow)] focus:shadow-[0_0_20px_rgba(231,197,154,0.16)]"
      />
      <button
        type="button"
        aria-label="Voice input"
        className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl border border-[var(--color-border)] bg-[rgba(231,197,154,0.12)] text-[var(--color-amber-glow)] transition-colors hover:border-[var(--color-amber-glow)]"
      >
        ◉
      </button>
      <button
        type="submit"
        className="mono min-h-12 shrink-0 rounded-xl border border-[var(--color-border)] px-4 text-[10px] uppercase tracking-[0.14em] text-[var(--color-polar-white)] transition-colors hover:border-[var(--color-amber-glow)] hover:text-[var(--color-amber-glow)] md:text-xs"
      >
        Отправить
      </button>
    </form>
  );
}
