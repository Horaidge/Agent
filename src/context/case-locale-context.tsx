"use client";

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type Dispatch,
  type ReactNode,
  type SetStateAction,
} from "react";
import type { Locale } from "@/content/enterprise-cases";

type CaseLocaleContextValue = {
  locale: Locale;
  setLocale: Dispatch<SetStateAction<Locale>>;
};

const CaseLocaleContext = createContext<CaseLocaleContextValue | null>(null);

export function CaseLocaleProvider({ children }: { children: ReactNode }) {
  const [locale, setLocale] = useState<Locale>("ru");
  const value = useMemo(() => ({ locale, setLocale }), [locale]);
  return <CaseLocaleContext.Provider value={value}>{children}</CaseLocaleContext.Provider>;
}

export function useCaseLocale(): CaseLocaleContextValue {
  const ctx = useContext(CaseLocaleContext);
  if (!ctx) {
    throw new Error("useCaseLocale must be used within CaseLocaleProvider");
  }
  return ctx;
}

export function pickLocale<T extends Record<Locale, string>>(block: T, locale: Locale): string {
  return block[locale];
}
