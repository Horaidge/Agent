"use client";

import { memo } from "react";
import LiquidEther from "@/components/liquid-ether";

/** Softened WebGL — very low intensity so it adds depth, not glare */
const ETHER_COLORS = ["#05070A", "#1a1030", "#0c1828"] as const;

export const AmbientBackground = memo(function AmbientBackground() {
  return (
    <div className="pointer-events-none fixed inset-0 z-0 overflow-hidden" aria-hidden>
      {/* Base */}
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: "#05070A",
          backgroundImage: `
            radial-gradient(ellipse 80% 55% at 50% 18%, rgba(88, 60, 160, 0.14), transparent 55%),
            radial-gradient(ellipse 70% 50% at 80% 70%, rgba(34, 90, 120, 0.08), transparent 50%),
            radial-gradient(ellipse 60% 45% at 15% 75%, rgba(100, 70, 180, 0.06), transparent 45%)
          `,
        }}
      />

      {/* Subtle fluid layer */}
      <div className="absolute inset-0 opacity-[0.14]">
        <LiquidEther
          colors={ETHER_COLORS as unknown as string[]}
          mouseForce={6}
          cursorSize={80}
          isViscous={false}
          resolution={0.45}
          autoDemo
          autoSpeed={0.18}
          autoIntensity={0.55}
          autoResumeDelay={4000}
        />
      </div>

      {/* Grain */}
      <div
        className="noise-overlay absolute inset-0 opacity-[0.045]"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E")`,
          backgroundRepeat: "repeat",
          backgroundSize: "128px 128px",
        }}
      />

      {/* Bottom vignette */}
      <div
        className="absolute inset-0"
        style={{
          background:
            "linear-gradient(to bottom, transparent 0%, transparent 55%, rgba(5, 7, 10, 0.65) 100%)",
        }}
      />
    </div>
  );
});
