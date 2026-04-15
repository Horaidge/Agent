'use client';

import { motion } from 'framer-motion';

interface TopBarProps {
  onNavClick?: (section: string) => void;
  activeSection?: string | null;
}

export function TopBar({ onNavClick, activeSection }: TopBarProps) {
  // Navigation items
  const navItems = ['Platform', 'Use Cases', 'How It Works'];

  return (
    <motion.header
      className="relative z-20 w-full border-b border-border/20"
      style={{ background: 'rgba(5, 6, 10, 0.8)', backdropFilter: 'blur(8px)' }}
      initial={{ y: -20, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: 0.6, ease: [0.32, 0.72, 0, 1] }}
    >
      <div className="flex items-center justify-between px-6 py-4">
        {/* Left: Branding */}
        <div className="flex flex-col gap-1">
          <h1 className="text-xl font-bold text-foreground">Dzen.AI</h1>
          <p className="text-xs text-muted-foreground">AI agents that act, not just answer</p>
        </div>

        {/* Right: Navigation */}
        <nav className="hidden md:flex items-center gap-6">
          {navItems.map((item, index) => {
            const isActive = activeSection === item;

            return (
              <motion.button
                key={item}
                onClick={() => onNavClick?.(item)}
                // Prevent white flash with neutral focus styles
                className="relative text-sm text-muted-foreground hover:text-foreground transition-colors focus:outline-none"
                style={{
                  // Remove default focus ring
                  WebkitTapHighlightColor: 'transparent',
                }}
                whileHover={{ y: -2 }}
                whileTap={{ scale: 0.95 }}
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.1 * (index + 1), duration: 0.4 }}
              >
                {item}

                {/* Soft indicator line for active state */}
                {isActive && (
                  <motion.div
                    className="absolute bottom-0 left-0 right-0 h-px"
                    style={{ background: 'rgba(124, 58, 237, 0.4)' }}
                    layoutId="nav-indicator"
                    transition={{ duration: 0.25 }}
                  />
                )}
              </motion.button>
            );
          })}
        </nav>
      </div>
    </motion.header>
  );
}
