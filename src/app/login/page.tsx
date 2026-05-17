import Link from "next/link";
import { UIButton } from "@/components/ui/button";

export default function LoginPage() {
  return (
    <main className="flex min-h-dvh items-center justify-center bg-[var(--color-midnight-void)] px-6">
      <div className="w-full max-w-md rounded-xl border border-[var(--color-border)] bg-[var(--color-deep-space)] p-6">
        <p className="mono mb-2 text-xs uppercase tracking-[0.18em] text-[var(--color-ash-gray)]">
          admin access
        </p>
        <h1 className="mb-2 text-2xl">Login placeholder</h1>
        <p className="mb-5 text-sm text-[var(--color-ash-gray)]">
          Реальная авторизация будет подключена в следующих этапах.
        </p>
        <div className="grid gap-3">
          <input
            type="email"
            disabled
            placeholder="email"
            className="rounded border border-[var(--color-border)] bg-transparent p-2 text-sm"
          />
          <input
            type="password"
            disabled
            placeholder="password"
            className="rounded border border-[var(--color-border)] bg-transparent p-2 text-sm"
          />
          <Link href="/admin">
            <UIButton variant="primaryGhost" className="w-full border border-[var(--color-border)]">
              Enter admin
            </UIButton>
          </Link>
        </div>
      </div>
    </main>
  );
}
