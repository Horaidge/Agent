"use client"

import { 
  Mic, 
  MessageCircle, 
  Cpu, 
  Plug, 
  BookOpen, 
  Cloud 
} from "lucide-react"
import { useLanguage } from "@/lib/language-context"

export function CapabilitiesSection() {
  const { t } = useLanguage()

  const capabilities = [
    {
      icon: Mic,
      titleKey: "capabilities.voice.title",
      descriptionKey: "capabilities.voice.description",
    },
    {
      icon: MessageCircle,
      titleKey: "capabilities.omni.title",
      descriptionKey: "capabilities.omni.description",
    },
    {
      icon: Cpu,
      titleKey: "capabilities.reasoning.title",
      descriptionKey: "capabilities.reasoning.description",
    },
    {
      icon: Plug,
      titleKey: "capabilities.integrations.title",
      descriptionKey: "capabilities.integrations.description",
    },
    {
      icon: BookOpen,
      titleKey: "capabilities.rag.title",
      descriptionKey: "capabilities.rag.description",
    },
    {
      icon: Cloud,
      titleKey: "capabilities.deployment.title",
      descriptionKey: "capabilities.deployment.description",
    },
  ]

  return (
    <section id="solutions" className="py-20 px-4 sm:px-6 lg:px-8">
      <div className="max-w-7xl mx-auto">
        <div className="text-center mb-16">
          <h2 className="text-3xl sm:text-4xl font-bold text-foreground mb-4 text-balance">
            {t("capabilities.title")}
          </h2>
          <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
            {t("capabilities.subtitle")}
          </p>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-6 lg:gap-8">
          {capabilities.map((capability) => (
            <div 
              key={capability.titleKey} 
              className="flex flex-col items-center text-center p-4 rounded-2xl hover:bg-muted/50 transition-colors group"
            >
              <div className="w-14 h-14 rounded-2xl bg-primary/10 flex items-center justify-center mb-4 group-hover:bg-primary/20 transition-colors">
                <capability.icon className="w-7 h-7 text-primary" />
              </div>
              <h3 className="font-semibold text-foreground mb-1 text-sm">{t(capability.titleKey)}</h3>
              <p className="text-xs text-muted-foreground leading-relaxed">{t(capability.descriptionKey)}</p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
