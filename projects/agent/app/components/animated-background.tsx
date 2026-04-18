"use client";

import { motion } from "framer-motion";

export function AnimatedBackground() {
  return (
    <div className="fixed inset-0 z-0 overflow-hidden bg-background">
      {/* Base gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-[#05060A] via-[#0a0814] to-[#05060A]" />

      {/* Animated violet orb — top center */}
      <motion.div
        className="absolute top-0 left-1/2 w-96 h-96 rounded-full blur-3xl pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(124,58,237,0.15) 0%, transparent 70%)",
          transform: "translateX(-50%)",
        }}
        animate={{
          y: [-50, 50, -50],
          opacity: [0.3, 0.5, 0.3],
        }}
        transition={{
          duration: 8,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Animated cyan orb — bottom right */}
      <motion.div
        className="absolute bottom-0 right-0 w-80 h-80 rounded-full blur-3xl pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(34,211,238,0.12) 0%, transparent 70%)",
        }}
        animate={{
          y: [50, -50, 50],
          x: [50, -50, 50],
          opacity: [0.2, 0.4, 0.2],
        }}
        transition={{
          duration: 10,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Animated violet accent — left side */}
      <motion.div
        className="absolute top-1/3 -left-32 w-64 h-64 rounded-full blur-3xl pointer-events-none"
        style={{
          background: "radial-gradient(circle, rgba(124,58,237,0.1) 0%, transparent 70%)",
        }}
        animate={{
          x: [-100, 50, -100],
          opacity: [0.25, 0.4, 0.25],
        }}
        transition={{
          duration: 9,
          repeat: Infinity,
          ease: "easeInOut",
        }}
      />

      {/* Grid pattern overlay — subtle */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          backgroundImage: `
            linear-gradient(rgba(124,58,237,0.03) 1px, transparent 1px),
            linear-gradient(90deg, rgba(124,58,237,0.03) 1px, transparent 1px)
          `,
          backgroundSize: "80px 80px",
        }}
      />
    </div>
  );
}
