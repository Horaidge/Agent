"use client"

import { Button } from "@/components/ui/button"
import { ArrowDown } from "lucide-react"
import { useLanguage } from "@/lib/language-context"
import Link from "next/link"

export function HeroSection() {
  const { t } = useLanguage()

  return (
    <section className="pt-32 pb-20 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto text-center">
        <h1 className="text-4xl sm:text-5xl lg:text-6xl font-bold text-foreground mb-6 text-balance">
          {t("hero.title")}
        </h1>
        <p className="text-xl text-muted-foreground mb-10 max-w-2xl mx-auto">
          {t("hero.subtitle")}
        </p>
        <Link href="#platform">
          <Button size="lg" className="gap-2">
            {t("hero.cta")}
            <ArrowDown className="w-4 h-4" />
          </Button>
        </Link>
      </div>
    </section>
  )
}
