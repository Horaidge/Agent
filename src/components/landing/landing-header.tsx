export function LandingHeader() {
  return (
    <header className="sticky top-0 z-20 border-b border-[var(--color-border)] bg-[rgba(16,16,16,0.86)] backdrop-blur">
      <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-4">
        <div className="mono text-xs uppercase tracking-[0.18em] text-[var(--color-amber-glow)]">
          DZEN.AI
        </div>
        <nav className="flex items-center gap-4 text-sm text-[var(--color-ash-gray)]">
          <a href="#agent-zone" className="hover:text-[var(--color-polar-white)]">
            Agent Interface
          </a>
          <a href="#portfolio" className="hover:text-[var(--color-polar-white)]">
            Systems
          </a>
          <a href="#use-cases" className="hover:text-[var(--color-polar-white)]">
            Use Cases
          </a>
          <a href="#contact" className="hover:text-[var(--color-polar-white)]">
            Request Demo
          </a>
        </nav>
      </div>
    </header>
  );
}
