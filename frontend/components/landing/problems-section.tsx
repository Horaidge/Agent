"use client"

import { Card, CardContent } from "@/components/ui/card"
import { TrendingUp, Database, Server } from "lucide-react"
import { useLanguage } from "@/lib/language-context"

export function ProblemsSection() {
  const { t } = useLanguage()

  const problems = [
    {
      icon: TrendingUp,
      titleKey: "problems.cost.title",
      descriptionKey: "problems.cost.description",
    },
    {
      icon: Database,
      titleKey: "problems.knowledge.title",
      descriptionKey: "problems.knowledge.description",
    },
    {
      icon: Server,
      titleKey: "problems.legacy.title",
      descriptionKey: "problems.legacy.description",
    },
  ]

  return (
    <section className="py-20 px-4 sm:px-6 lg:px-8 bg-muted/30">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4 text-balance">
            {t("problems.title")}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t("problems.subtitle")}
          </p>
        </div>

        <div className="grid md:grid-cols-3 gap-6 lg:gap-8">
          {problems.map((problem) => (
            <Card key={problem.titleKey} className="bg-card border-border hover:border-primary/20 transition-colors group">
              <CardContent className="p-6 lg:p-8">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-6 group-hover:bg-primary/20 transition-colors">
                  <problem.icon className="w-6 h-6 text-primary" />
                </div>
                <h3 className="text-xl font-semibold text-foreground mb-3">{t(problem.titleKey)}</h3>
                <p className="text-muted-foreground leading-relaxed">{t(problem.descriptionKey)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
