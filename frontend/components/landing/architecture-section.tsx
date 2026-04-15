"use client"

import { ArrowRight } from "lucide-react"
import { useLanguage } from "@/lib/language-context"

export function ArchitectureSection() {
  const { t } = useLanguage()

  const architectureBlocks = [
    { id: "user", labelKey: "architecture.user", color: "bg-foreground text-background" },
    { id: "router", labelKey: "architecture.router", color: "bg-primary text-primary-foreground" },
    { id: "knowledge", labelKey: "architecture.knowledge", color: "bg-primary/80 text-primary-foreground" },
    { id: "skill", labelKey: "architecture.skill", color: "bg-primary/60 text-primary-foreground" },
    { id: "enterprise", labelKey: "architecture.enterprise", color: "bg-muted text-foreground border border-border" },
  ]

  return (
    <section id="platform" className="py-20 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4 text-balance">
            {t("architecture.title")}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t("architecture.subtitle")}
          </p>
        </div>

        {/* Architecture Diagram */}
        <div className="relative">
          {/* Desktop view */}
          <div className="hidden md:flex items-center justify-center gap-4 lg:gap-6">
            {architectureBlocks.map((block, index) => (
              <div key={block.id} className="flex items-center gap-4 lg:gap-6">
                <div className={`px-6 py-4 rounded-xl ${block.color} font-medium text-center min-w-[140px] lg:min-w-[160px] shadow-sm`}>
                  {t(block.labelKey)}
                </div>
                {index < architectureBlocks.length - 1 && (
                  <ArrowRight className="w-5 h-5 text-muted-foreground shrink-0" />
                )}
              </div>
            ))}
          </div>

          {/* Mobile view - vertical layout */}
          <div className="md:hidden flex flex-col items-center gap-4">
            {architectureBlocks.map((block, index) => (
              <div key={block.id} className="flex flex-col items-center gap-4">
                <div className={`px-6 py-4 rounded-xl ${block.color} font-medium text-center w-full max-w-[200px] shadow-sm`}>
                  {t(block.labelKey)}
                </div>
                {index < architectureBlocks.length - 1 && (
                  <ArrowRight className="w-5 h-5 text-muted-foreground rotate-90" />
                )}
              </div>
            ))}
          </div>

          {/* Decorative background */}
          <div className="absolute inset-0 -z-10 bg-gradient-to-r from-primary/5 via-transparent to-primary/5 rounded-3xl" />
        </div>

        {/* Architecture description */}
        <div className="mt-16 grid md:grid-cols-3 gap-8 text-center">
          <div>
            <h3 className="font-semibold text-foreground mb-2">{t("architecture.routing.title")}</h3>
            <p className="text-sm text-muted-foreground">
              {t("architecture.routing.description")}
            </p>
          </div>
          <div>
            <h3 className="font-semibold text-foreground mb-2">{t("architecture.access.title")}</h3>
            <p className="text-sm text-muted-foreground">
              {t("architecture.access.description")}
            </p>
          </div>
          <div>
            <h3 className="font-semibold text-foreground mb-2">{t("architecture.action.title")}</h3>
            <p className="text-sm text-muted-foreground">
              {t("architecture.action.description")}
            </p>
          </div>
        </div>
      </div>
    </section>
  )
}
