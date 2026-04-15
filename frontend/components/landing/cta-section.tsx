"use client"

import { Button } from "@/components/ui/button"
import { ArrowRight, Mic } from "lucide-react"
import { useLanguage } from "@/lib/language-context"
import { dispatchOpenChat } from "@/lib/chat-events"

export function CTASection() {
  const { t } = useLanguage()

  return (
    <section className="py-20 px-4 sm:px-6 lg:px-8">
      <div className="max-w-4xl mx-auto">
        <div className="relative bg-foreground text-background rounded-3xl p-8 lg:p-16 overflow-hidden">
          {/* Background decoration */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-primary/20 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute bottom-0 left-0 w-48 h-48 bg-primary/10 rounded-full blur-2xl pointer-events-none" />
          
          <div className="relative z-10 text-center">
            <h2 className="text-3xl sm:text-4xl lg:text-5xl font-bold mb-6 text-balance">
              {t("cta.title")}
            </h2>
            <p className="text-lg text-background/70 mb-10 max-w-2xl mx-auto">
              {t("cta.subtitle")}
            </p>
            
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
              <Button size="lg" variant="secondary" className="gap-2 text-base px-8">
                {t("cta.bookDemo")}
                <ArrowRight className="w-4 h-4" />
              </Button>
              <Button size="lg" variant="outline" className="gap-2 text-base px-8 bg-transparent border-background/30 text-background hover:bg-background/10 hover:text-background" onClick={dispatchOpenChat}>
                <Mic className="w-4 h-4" />
                {t("cta.talkToAgent")}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
