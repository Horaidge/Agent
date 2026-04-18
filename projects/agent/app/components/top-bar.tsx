"use client";

import { motion } from "framer-motion";

const NAV = ["Platform", "Use Cases", "How It Works"] as const;

interface TopBarProps {
  onNavClick?: (section: string) => void;
  activeSection?: string | null;
}

export function TopBar({ onNavClick, activeSection }: TopBarProps) {
  return (
    <motion.header
      className="fixed top-0 left-0 right-0 z-50 border-b"
      style={{
        background: "rgba(5, 7, 10, 0.55)",
        borderColor: "rgba(255,255,255,0.06)",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
      }}
      initial={{ y: -12, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.45, ease: [0.32, 0.72, 0, 1] }}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between gap-6 px-5 py-3.5 md:px-8">
        <div className="flex min-w-0 flex-col gap-0.5">
          <span className="text-lg font-semibold tracking-tight text-[rgba(232,234,240,0.96)]">Dzen.AI</span>
          <span className="text-[11px] font-light tracking-wide text-[rgba(160,168,192,0.55)]">
            AI agents that act, not just answer
          </span>
        </div>

        <nav className="hidden items-center gap-1 md:flex" aria-label="Primary">
          {NAV.map((item) => {
            const isActive = activeSection === item;
            return (
              <button
                key={item}
                type="button"
                onClick={() => onNavClick?.(item)}
                className="group relative rounded-lg px-3 py-2 text-sm transition-colors duration-200"
                style={{
                  color: isActive ? "rgba(232,234,240,0.95)" : "rgba(160,168,192,0.72)",
                  background: isActive ? "rgba(124,92,200,0.12)" : "transparent",
                }}
              >
                <span className="relative z-[1]">{item}</span>
                {!isActive && (
                  <span
                    className="pointer-events-none absolute inset-0 rounded-lg opacity-0 transition-opacity duration-200 group-hover:opacity-100"
                    style={{ background: "rgba(255,255,255,0.04)" }}
                  />
                )}
                {isActive && (
                  <motion.span
                    layoutId="nav-pill"
                    className="absolute inset-0 rounded-lg ring-1 ring-[rgba(124,92,200,0.25)]"
                    style={{ background: "rgba(124,92,200,0.08)" }}
                    transition={{ type: "spring", stiffness: 380, damping: 32 }}
                  />
                )}
              </button>
            );
          })}
        </nav>
      </div>
    </motion.header>
  );
}
