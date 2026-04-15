"use client"

import { Database, GraduationCap, Rocket } from "lucide-react"
import { useLanguage } from "@/lib/language-context"

export function RoadmapSection() {
  const { t } = useLanguage()

  const steps = [
    {
      number: "01",
      icon: Database,
      durationKey: "roadmap.step1.duration",
      titleKey: "roadmap.step1.title",
      descriptionKey: "roadmap.step1.description",
    },
    {
      number: "02",
      icon: GraduationCap,
      durationKey: "roadmap.step2.duration",
      titleKey: "roadmap.step2.title",
      descriptionKey: "roadmap.step2.description",
    },
    {
      number: "03",
      icon: Rocket,
      durationKey: "roadmap.step3.duration",
      titleKey: "roadmap.step3.title",
      descriptionKey: "roadmap.step3.description",
    },
  ]

  return (
    <section className="py-20 px-4 sm:px-6 lg:px-8 bg-muted/30">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4 text-balance">
            {t("roadmap.title")}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t("roadmap.subtitle")}
          </p>
        </div>

        <div className="relative">
          {/* Timeline connector - desktop */}
          <div className="hidden lg:block absolute top-1/2 left-0 right-0 h-0.5 bg-border -translate-y-1/2" />
          
          <div className="grid lg:grid-cols-3 gap-8 lg:gap-12">
            {steps.map((step, index) => (
              <div key={step.number} className="relative">
                {/* Mobile connector */}
                {index < steps.length - 1 && (
                  <div className="lg:hidden absolute left-6 top-16 bottom-0 w-0.5 bg-border -translate-x-1/2" />
                )}
                
                <div className="flex lg:flex-col items-start lg:items-center gap-4 lg:gap-0">
                  {/* Step number circle */}
                  <div className="relative z-10 w-12 h-12 lg:w-16 lg:h-16 rounded-full bg-primary flex items-center justify-center shrink-0 lg:mb-6">
                    <step.icon className="w-6 h-6 lg:w-8 lg:h-8 text-primary-foreground" />
                  </div>
                  
                  <div className="lg:text-center">
                    <div className="text-xs font-medium text-primary mb-1">{t(step.durationKey)}</div>
                    <h3 className="text-xl font-semibold text-foreground mb-2">{t(step.titleKey)}</h3>
                    <p className="text-sm text-muted-foreground leading-relaxed lg:max-w-xs">
                      {t(step.descriptionKey)}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}
