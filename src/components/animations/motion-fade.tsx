"use client";

import { motion } from "framer-motion";
import type { PropsWithChildren } from "react";

type MotionFadeProps = PropsWithChildren<{
  delay?: number;
  className?: string;
}>;

export function MotionFade({ children, delay = 0, className = "" }: MotionFadeProps) {
  return (
    <motion.div
      className={className}
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay }}
    >
      {children}
    </motion.div>
  );
}
