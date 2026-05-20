"use client";

import { AnimatePresence, motion } from "framer-motion";
import type { PropsWithChildren } from "react";

type ChatPanelTransitionProps = PropsWithChildren<{
  open: boolean;
  className?: string;
}>;

export function ChatPanelTransition({ open, className = "", children }: ChatPanelTransitionProps) {
  return (
    <AnimatePresence initial={false}>
      {open ? (
        <motion.div
          layout
          className={className}
          initial={{ opacity: 0, y: 14, scale: 0.985 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 10, scale: 0.99 }}
          transition={{ duration: 0.46, ease: [0.22, 1, 0.36, 1] }}
        >
          {children}
        </motion.div>
      ) : null}
    </AnimatePresence>
  );
}
