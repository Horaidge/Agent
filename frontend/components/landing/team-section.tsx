"use client"

import { Users, Clock, Building2 } from "lucide-react"
import { useLanguage } from "@/lib/language-context"

export function TeamSection() {
  const { t } = useLanguage()

  const teamStats = [
    {
      icon: Users,
      valueKey: "team.specialists.value",
      labelKey: "team.specialists.label",
      descriptionKey: "team.specialists.description",
    },
    {
      icon: Clock,
      valueKey: "team.experience.value",
      labelKey: "team.experience.label",
      descriptionKey: "team.experience.description",
    },
    {
      icon: Building2,
      valueKey: "team.deployments.value",
      labelKey: "team.deployments.label",
      descriptionKey: "team.deployments.description",
    },
  ]

  return (
    <section id="about" className="py-20 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4 text-balance">
            {t("team.title")}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t("team.subtitle")}
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-8 lg:gap-12">
          {teamStats.map((stat) => (
            <div key={stat.labelKey} className="text-center">
              <div className="w-16 h-16 rounded-2xl bg-primary/10 flex items-center justify-center mx-auto mb-6">
                <stat.icon className="w-8 h-8 text-primary" />
              </div>
              <div className="text-4xl lg:text-5xl font-bold text-foreground mb-2">{t(stat.valueKey)}</div>
              <h3 className="text-lg font-semibold text-foreground mb-2">{t(stat.labelKey)}</h3>
              <p className="text-sm text-muted-foreground">{t(stat.descriptionKey)}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
