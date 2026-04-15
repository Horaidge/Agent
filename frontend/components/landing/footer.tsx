"use client"

import Link from "next/link"
import { useLanguage } from "@/lib/language-context"

export function Footer() {
  const { t } = useLanguage()

  const footerLinks = {
    product: [
      { labelKey: "footer.platform", href: "#platform" },
      { labelKey: "footer.solutions", href: "#solutions" },
      { labelKey: "footer.pricing", href: "#" },
      { labelKey: "footer.documentation", href: "#" },
    ],
    company: [
      { labelKey: "footer.about", href: "#about" },
      { labelKey: "footer.caseStudies", href: "#case-studies" },
      { labelKey: "footer.careers", href: "#" },
      { labelKey: "footer.contact", href: "#" },
    ],
    resources: [
      { labelKey: "footer.blog", href: "#" },
      { labelKey: "footer.apiReference", href: "#" },
      { labelKey: "footer.support", href: "#" },
      { labelKey: "footer.status", href: "#" },
    ],
    legal: [
      { labelKey: "footer.privacy", href: "#" },
      { labelKey: "footer.terms", href: "#" },
      { labelKey: "footer.security", href: "#" },
    ],
  }

  return (
    <footer className="border-t border-border bg-muted/30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12 lg:py-16">
        <div className="grid grid-cols-2 md:grid-cols-5 gap-8 lg:gap-12">
          {/* Logo and description */}
          <div className="col-span-2 md:col-span-1">
            <Link href="/" className="flex items-center gap-2 mb-4">
              <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
                <span className="text-primary-foreground font-bold text-sm">d</span>
              </div>
              <span className="font-semibold text-lg text-foreground">dzen.ai</span>
            </Link>
            <p className="text-sm text-muted-foreground">
              {t("footer.description")}
            </p>
          </div>

          {/* Product links */}
          <div>
            <h4 className="font-semibold text-foreground mb-4">{t("footer.product")}</h4>
            <ul className="space-y-3">
              {footerLinks.product.map((link) => (
                <li key={link.labelKey}>
                  <Link href={link.href} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                    {t(link.labelKey)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Company links */}
          <div>
            <h4 className="font-semibold text-foreground mb-4">{t("footer.company")}</h4>
            <ul className="space-y-3">
              {footerLinks.company.map((link) => (
                <li key={link.labelKey}>
                  <Link href={link.href} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                    {t(link.labelKey)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Resources links */}
          <div>
            <h4 className="font-semibold text-foreground mb-4">{t("footer.resources")}</h4>
            <ul className="space-y-3">
              {footerLinks.resources.map((link) => (
                <li key={link.labelKey}>
                  <Link href={link.href} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                    {t(link.labelKey)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>

          {/* Legal links */}
          <div>
            <h4 className="font-semibold text-foreground mb-4">{t("footer.legal")}</h4>
            <ul className="space-y-3">
              {footerLinks.legal.map((link) => (
                <li key={link.labelKey}>
                  <Link href={link.href} className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                    {t(link.labelKey)}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <div className="border-t border-border mt-12 pt-8">
          <p className="text-sm text-muted-foreground text-center sm:text-left">
            © {new Date().getFullYear()} {t("footer.copyright")}
          </p>
        </div>
      </div>
    </footer>
  )
}
