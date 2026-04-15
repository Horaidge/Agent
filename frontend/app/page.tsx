"use client"

import { LanguageProvider } from "@/lib/language-context"
import { Header } from "@/components/landing/header"
import { HeroSection } from "@/components/landing/hero-section"
import { ProblemsSection } from "@/components/landing/problems-section"
import { ArchitectureSection } from "@/components/landing/architecture-section"
import { PlatformComponentsSection } from "@/components/landing/platform-components-section"
import { CapabilitiesSection } from "@/components/landing/capabilities-section"
import { CaseStudiesSection } from "@/components/landing/case-studies-section"
import { RoadmapSection } from "@/components/landing/roadmap-section"
import { TeamSection } from "@/components/landing/team-section"
import { CTASection } from "@/components/landing/cta-section"
import { Footer } from "@/components/landing/footer"
import { ChatWidget } from "@/components/chat-widget"

export default function LandingPage() {
  return (
    <LanguageProvider>
      <div className="min-h-screen bg-background">
        <Header />
        <main>
          <HeroSection />
          <ProblemsSection />
          <ArchitectureSection />
          <PlatformComponentsSection />
          <CapabilitiesSection />
          <CaseStudiesSection />
          <RoadmapSection />
          <TeamSection />
          <CTASection />
        </main>
        <Footer />
        <ChatWidget />
      </div>
    </LanguageProvider>
  )
}
