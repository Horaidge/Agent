import type { PropsWithChildren } from "react";
import Link from "next/link";

export default function AdminLayout({ children }: PropsWithChildren) {
  return (
    <div className="min-h-dvh bg-[var(--color-midnight-void)] text-[var(--color-polar-white)]">
      <header className="border-b border-[var(--color-border)]">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
          <p className="mono text-xs uppercase tracking-[0.18em] text-[var(--color-amber-glow)]">
            Admin panel
          </p>
          <Link className="text-sm text-[var(--color-ash-gray)] hover:text-[var(--color-polar-white)]" href="/">
            Back to site
          </Link>
        </div>
      </header>
      <div className="mx-auto w-full max-w-6xl px-6 py-8">{children}</div>
    </div>
  );
}
