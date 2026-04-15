"use client"

import { Card, CardContent } from "@/components/ui/card"
import { useLanguage } from "@/lib/language-context"

export function CaseStudiesSection() {
  const { t } = useLanguage()

  const caseStudies = [
    {
      metricKey: "caseStudies.nps.metric",
      labelKey: "caseStudies.nps.label",
      descriptionKey: "caseStudies.nps.description",
      companyKey: "caseStudies.nps.company",
    },
    {
      metricKey: "caseStudies.automation.metric",
      labelKey: "caseStudies.automation.label",
      descriptionKey: "caseStudies.automation.description",
      companyKey: "caseStudies.automation.company",
    },
    {
      metricKey: "caseStudies.cost.metric",
      labelKey: "caseStudies.cost.label",
      descriptionKey: "caseStudies.cost.description",
      companyKey: "caseStudies.cost.company",
    },
    {
      metricKey: "caseStudies.response.metric",
      labelKey: "caseStudies.response.label",
      descriptionKey: "caseStudies.response.description",
      companyKey: "caseStudies.response.company",
    },
  ]

  return (
    <section id="case-studies" className="py-20 px-4 sm:px-6 lg:px-8 bg-muted/30">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4 text-balance">
            {t("caseStudies.title")}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t("caseStudies.subtitle")}
          </p>
        </div>

        <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
          {caseStudies.map((study) => (
            <Card key={study.labelKey} className="bg-card border-border hover:border-primary/20 transition-all group overflow-hidden">
              <CardContent className="p-6">
                <div className="text-4xl lg:text-5xl font-bold text-primary mb-2 group-hover:scale-105 transition-transform origin-left">
                  {t(study.metricKey)}
                </div>
                <h3 className="font-semibold text-foreground mb-2">{t(study.labelKey)}</h3>
                <p className="text-sm text-muted-foreground mb-4 leading-relaxed">{t(study.descriptionKey)}</p>
                <div className="text-xs text-muted-foreground/70 border-t border-border pt-3">
                  {t(study.companyKey)}
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}
