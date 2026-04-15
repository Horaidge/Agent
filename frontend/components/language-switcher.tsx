"use client"

import { useLanguage, type Language } from "@/lib/language-context"
import { Globe } from "lucide-react"

export function LanguageSwitcher() {
  const { language, setLanguage } = useLanguage()

  const toggleLanguage = () => {
    setLanguage(language === "ru" ? "en" : "ru")
  }

  return (
    <button
      onClick={toggleLanguage}
      className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-muted hover:bg-muted/80 transition-colors text-sm font-medium text-foreground"
      aria-label="Switch language"
    >
      <Globe className="w-4 h-4" />
      <span className="uppercase">{language === "ru" ? "EN" : "RU"}</span>
    </button>
  )
}
