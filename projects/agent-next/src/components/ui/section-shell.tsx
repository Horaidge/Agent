import type { PropsWithChildren } from "react";

type SectionShellProps = PropsWithChildren<{
  id: string;
  title: string;
  subtitle?: string;
  className?: string;
  maxWidthClassName?: string;
}>;

export function SectionShell({
  id,
  title,
  subtitle,
  className = "",
  maxWidthClassName = "max-w-6xl",
  children,
}: SectionShellProps) {
  return (
    <section id={id} className={`border-t border-[var(--color-border)] px-6 py-16 ${className}`}>
      <div className={`mx-auto flex w-full flex-col gap-6 ${maxWidthClassName}`}>
        <header className="flex flex-col gap-2">
          <p className="mono text-[var(--text-caption)] uppercase tracking-[0.12em] text-[var(--color-ash-gray)]">
            {subtitle ?? "Hyperstudio"}
          </p>
          <h2 className="text-2xl">{title}</h2>
        </header>
        {children}
      </div>
    </section>
  );
}
