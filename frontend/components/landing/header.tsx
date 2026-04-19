"use client"

import { useState } from "react"
import Link from "next/link"
import { Button } from "@/components/ui/button"
import { Menu, X } from "lucide-react"
import { LanguageSwitcher } from "@/components/language-switcher"
import { useLanguage } from "@/lib/language-context"

export function Header() {
  const [isMenuOpen, setIsMenuOpen] = useState(false)
  const { t } = useLanguage()

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-background/80 backdrop-blur-md border-b border-border">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
              <span className="text-primary-foreground font-bold text-sm">d</span>
            </div>
            <span className="font-semibold text-lg text-foreground">dzen.ai</span>
          </Link>

          <nav className="hidden md:flex items-center gap-8">
            <Link href="#platform" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              {t("nav.platform")}
            </Link>
            <Link href="#solutions" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              {t("nav.solutions")}
            </Link>
            <Link href="#case-studies" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              {t("nav.caseStudies")}
            </Link>
            <Link href="#about" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
              {t("nav.about")}
            </Link>
          </nav>

          <div className="hidden md:flex items-center gap-3">
            <Link
              href="/prompt-editor"
              className="text-xs text-muted-foreground hover:text-foreground transition-colors"
            >
              Промпты
            </Link>
            <LanguageSwitcher />
          </div>

          <div className="md:hidden flex items-center gap-2">
            <Link
              href="/prompt-editor"
              className="text-xs text-muted-foreground px-1"
            >
              Промпты
            </Link>
            <LanguageSwitcher />
            <button
              className="p-2"
              onClick={() => setIsMenuOpen(!isMenuOpen)}
              aria-label="Toggle menu"
            >
              {isMenuOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
            </button>
          </div>
        </div>

        {isMenuOpen && (
          <div className="md:hidden py-4 border-t border-border">
            <nav className="flex flex-col gap-4">
              <Link href="/prompt-editor" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                Промпты
              </Link>
              <Link href="#platform" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                {t("nav.platform")}
              </Link>
              <Link href="#solutions" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                {t("nav.solutions")}
              </Link>
              <Link href="#case-studies" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                {t("nav.caseStudies")}
              </Link>
              <Link href="#about" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                {t("nav.about")}
              </Link>
            </nav>
          </div>
        )}
      </div>
    </header>
  )
}
