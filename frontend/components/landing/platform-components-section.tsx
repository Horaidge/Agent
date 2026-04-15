"use client"

import { Card, CardContent } from "@/components/ui/card"
import { 
  GitBranch, 
  Brain, 
  Search, 
  Zap, 
  GraduationCap, 
  ArrowLeftRight 
} from "lucide-react"
import { useLanguage } from "@/lib/language-context"

export function PlatformComponentsSection() {
  const { t } = useLanguage()

  const components = [
    {
      icon: GitBranch,
      titleKey: "platform.router.title",
      descriptionKey: "platform.router.description",
    },
    {
      icon: Brain,
      titleKey: "platform.knowledge.title",
      descriptionKey: "platform.knowledge.description",
    },
    {
      icon: Search,
      titleKey: "platform.knowledgeAgents.title",
      descriptionKey: "platform.knowledgeAgents.description",
    },
    {
      icon: Zap,
      titleKey: "platform.skillAgents.title",
      descriptionKey: "platform.skillAgents.description",
    },
    {
      icon: GraduationCap,
      titleKey: "platform.training.title",
      descriptionKey: "platform.training.description",
    },
    {
      icon: ArrowLeftRight,
      titleKey: "platform.transaction.title",
      descriptionKey: "platform.transaction.description",
    },
  ]

  return (
    <section className="py-20 px-4 sm:px-6 lg:px-8 bg-muted/30">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4 text-balance">
            {t("platform.title")}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t("platform.subtitle")}
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-6">
          {components.map((component) => (
            <Card key={component.titleKey} className="bg-card border-border hover:shadow-lg hover:border-primary/20 transition-all group">
              <CardContent className="p-6">
                <div className="w-12 h-12 rounded-xl bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary group-hover:scale-105 transition-all">
                  <component.icon className="w-6 h-6 text-primary group-hover:text-primary-foreground transition-colors" />
                </div>
                <h3 className="text-lg font-semibold text-foreground mb-2">{t(component.titleKey)}</h3>
                <p className="text-sm text-muted-foreground leading-relaxed">{t(component.descriptionKey)}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
