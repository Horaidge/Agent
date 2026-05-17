"use client";

import type { ButtonHTMLAttributes, PropsWithChildren } from "react";

type ButtonVariant = "primaryGhost" | "secondaryGhost";

type UIButtonProps = PropsWithChildren<
  ButtonHTMLAttributes<HTMLButtonElement> & {
    variant?: ButtonVariant;
  }
>;

const variantClassMap: Record<ButtonVariant, string> = {
  primaryGhost:
    "text-[var(--color-polar-white)] hover:text-[var(--color-absolute-zero)]",
  secondaryGhost: "text-[var(--color-ash-gray)] hover:text-[var(--color-polar-white)]",
};

export function UIButton({ children, className = "", variant = "primaryGhost", ...rest }: UIButtonProps) {
  return (
    <button
      className={`rounded-[var(--radius-default)] px-4 py-2 text-sm transition-colors ${variantClassMap[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
