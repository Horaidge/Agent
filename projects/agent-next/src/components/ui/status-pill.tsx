type StatusPillProps = {
  children: string;
  tone?: "neutral" | "positive";
};

export function StatusPill({ children, tone = "neutral" }: StatusPillProps) {
  const toneClass =
    tone === "positive"
      ? "bg-[var(--color-neon-green)] text-[var(--color-polar-white)]"
      : "bg-[var(--color-dark-carbon)] text-[var(--color-polar-white)]";

  return (
    <span
      className={`inline-flex items-center rounded-[var(--radius-pill)] px-3 py-1 text-[var(--text-caption)] tracking-wide ${toneClass}`}
    >
      {children}
    </span>
  );
}
