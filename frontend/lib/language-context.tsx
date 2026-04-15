"use client"

import React, { createContext, useContext, useState, useCallback } from "react"

export type Language = "ru" | "en"

type Translations = Record<string, string>

function flattenKeys(obj: Record<string, unknown>, prefix = ""): Translations {
  const result: Translations = {}
  for (const [key, value] of Object.entries(obj)) {
    const fullKey = prefix ? `${prefix}.${key}` : key
    if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      Object.assign(result, flattenKeys(value as Record<string, unknown>, fullKey))
    } else {
      result[fullKey] = String(value)
    }
  }
  return result
}

const translations: Record<Language, Record<string, string>> = {
  ru: flattenKeys({
    nav: {
      platform: "Платформа",
      solutions: "Решения",
      caseStudies: "Кейсы",
      about: "О нас",
    },
    hero: {
      title: "Корпоративные AI-агенты для бизнеса",
      subtitle: "Голосовые и мультимодальные агенты, которые решают реальные задачи.",
      cta: "Узнать больше",
    },
    problems: {
      title: "Проблемы, которые мы решаем",
      subtitle: "Корпоративные системы сталкиваются с типичными вызовами при внедрении AI",
      cost: {
        title: "Высокие затраты",
        description: "Собственная инфраструктура и модели требуют значительных инвестиций.",
      },
      knowledge: {
        title: "Разрозненные знания",
        description: "Критичная информация хранится в разных системах и форматах.",
      },
      legacy: {
        title: "Устаревшие системы",
        description: "Интеграция AI с существующими бизнес-процессами затруднена.",
      },
    },
    architecture: {
      title: "Архитектура платформы",
      subtitle: "Модульная система для гибкого развёртывания корпоративного AI",
      user: "Пользователь",
      router: "Роутер",
      knowledge: "База знаний",
      skill: "Навыки",
      enterprise: "Enterprise-системы",
      routing: {
        title: "Интеллектуальная маршрутизация",
        description: "Запросы направляются к нужным агентам и источникам знаний.",
      },
      access: {
        title: "Единый доступ",
        description: "Один интерфейс для работы со всеми корпоративными данными.",
      },
      action: {
        title: "Действия и интеграции",
        description: "Агенты выполняют транзакции и интегрируются с бизнес-системами.",
      },
    },
    platform: {
      title: "Компоненты платформы",
      subtitle: "Всё необходимое для создания и масштабирования AI-решений",
      router: {
        title: "Умный роутер",
        description: "Направляет запросы к соответствующим агентам и источникам данных.",
      },
      knowledge: {
        title: "База знаний",
        description: "Централизованное хранилище корпоративных знаний с RAG.",
      },
      knowledgeAgents: {
        title: "Агенты знаний",
        description: "Поиск и синтез информации из документации и баз данных.",
      },
      skillAgents: {
        title: "Агенты навыков",
        description: "Выполнение задач: бронирования, расчёты, автоматизация.",
      },
      training: {
        title: "Обучение и fine-tuning",
        description: "Адаптация моделей под специфику вашего бизнеса.",
      },
      transaction: {
        title: "Транзакционная интеграция",
        description: "Связь с CRM, ERP и другими enterprise-системами.",
      },
    },
    capabilities: {
      title: "Возможности",
      subtitle: "Полный набор инструментов для корпоративного AI",
      voice: {
        title: "Голос",
        description: "Распознавание и синтез речи для звонков и голосовых ассистентов.",
      },
      omni: {
        title: "Omni-каналы",
        description: "Чат, мессенджеры, email — единый контекст диалога.",
      },
      reasoning: {
        title: "Рассуждения",
        description: "Многошаговый анализ и принятие решений.",
      },
      integrations: {
        title: "Интеграции",
        description: "API и коннекторы к популярным бизнес-системам.",
      },
      rag: {
        title: "RAG",
        description: "Retrieval-Augmented Generation для точных ответов.",
      },
      deployment: {
        title: "Развёртывание",
        description: "On-premise, облако или гибридная модель.",
      },
    },
    caseStudies: {
      title: "Кейсы и результаты",
      subtitle: "Реальные эффекты внедрения на корпоративных проектах",
      nps: {
        metric: "+32",
        label: "Рост NPS",
        description: "Улучшение удовлетворённости клиентов за счёт быстрых ответов.",
        company: "Крупный банк",
      },
      automation: {
        metric: "80%",
        label: "Автоматизация",
        description: "Доля обращений, решённых без участия оператора.",
        company: "Телеком",
      },
      cost: {
        metric: "-40%",
        label: "Снижение затрат",
        description: "Оптимизация расходов на поддержку и инфраструктуру.",
        company: "Ритейл",
      },
      response: {
        metric: "<5 с",
        label: "Время ответа",
        description: "Среднее время получения ответа клиентом.",
        company: "Страховая компания",
      },
    },
    roadmap: {
      title: "Дорожная карта",
      subtitle: "Этапы внедрения от пилота до масштабирования",
      step1: {
        duration: "2–4 недели",
        title: "Пилот",
        description: "Развёртывание на одном сценарии, оценка результата.",
      },
      step2: {
        duration: "1–2 месяца",
        title: "Обучение",
        description: "Подключение знаний, fine-tuning, интеграция с системами.",
      },
      step3: {
        duration: "3+ месяца",
        title: "Масштабирование",
        description: "Расширение на новые процессы и подразделения.",
      },
    },
    team: {
      title: "Наша команда",
      subtitle: "Опыт в AI, enterprise-системах и корпоративных проектах",
      specialists: {
        value: "50+",
        label: "Специалистов",
        description: "Инженеры, лингвисты, эксперты по доменным областям.",
      },
      experience: {
        value: "5+ лет",
        label: "Опыт",
        description: "В разработке и внедрении AI-решений.",
      },
      deployments: {
        value: "30+",
        label: "Внедрений",
        description: "Успешных проектов в крупных компаниях.",
      },
    },
    cta: {
      title: "Готовы обсудить проект?",
      subtitle: "Запишитесь на демо или пообщайтесь с нашим агентом",
      bookDemo: "Записаться на демо",
      talkToAgent: "Поговорить с агентом",
    },
    footer: {
      description: "Корпоративная AI-платформа для автоматизации и усиления бизнес-процессов.",
      product: "Продукт",
      company: "Компания",
      resources: "Ресурсы",
      legal: "Юридическая информация",
      copyright: "dzen.ai. Все права защищены.",
      platform: "Платформа",
      solutions: "Решения",
      pricing: "Цены",
      documentation: "Документация",
      about: "О нас",
      caseStudies: "Кейсы",
      careers: "Карьера",
      contact: "Контакты",
      blog: "Блог",
      apiReference: "API",
      support: "Поддержка",
      status: "Статус",
      privacy: "Конфиденциальность",
      terms: "Условия использования",
      security: "Безопасность",
    },
  }),
  en: flattenKeys({
    nav: {
      platform: "Platform",
      solutions: "Solutions",
      caseStudies: "Case Studies",
      about: "About",
    },
    hero: {
      title: "Enterprise AI Agents for Business",
      subtitle: "Voice and multimodal agents that solve real business problems.",
      cta: "Learn more",
    },
    problems: {
      title: "Problems We Solve",
      subtitle: "Enterprise systems face common challenges when adopting AI",
      cost: {
        title: "High Costs",
        description: "Own infrastructure and models require significant investment.",
      },
      knowledge: {
        title: "Fragmented Knowledge",
        description: "Critical information is stored across different systems and formats.",
      },
      legacy: {
        title: "Legacy Systems",
        description: "Integrating AI with existing business processes is challenging.",
      },
    },
    architecture: {
      title: "Platform Architecture",
      subtitle: "Modular system for flexible enterprise AI deployment",
      user: "User",
      router: "Router",
      knowledge: "Knowledge",
      skill: "Skills",
      enterprise: "Enterprise Systems",
      routing: {
        title: "Smart Routing",
        description: "Requests are routed to the right agents and knowledge sources.",
      },
      access: {
        title: "Unified Access",
        description: "Single interface for all corporate data.",
      },
      action: {
        title: "Actions & Integrations",
        description: "Agents perform transactions and integrate with business systems.",
      },
    },
    platform: {
      title: "Platform Components",
      subtitle: "Everything needed to build and scale AI solutions",
      router: {
        title: "Smart Router",
        description: "Routes requests to appropriate agents and data sources.",
      },
      knowledge: {
        title: "Knowledge Base",
        description: "Centralized corporate knowledge storage with RAG.",
      },
      knowledgeAgents: {
        title: "Knowledge Agents",
        description: "Search and synthesize information from docs and databases.",
      },
      skillAgents: {
        title: "Skill Agents",
        description: "Execute tasks: bookings, calculations, automation.",
      },
      training: {
        title: "Training & Fine-tuning",
        description: "Adapt models to your business specifics.",
      },
      transaction: {
        title: "Transaction Integration",
        description: "Connect with CRM, ERP and other enterprise systems.",
      },
    },
    capabilities: {
      title: "Capabilities",
      subtitle: "Full toolkit for enterprise AI",
      voice: {
        title: "Voice",
        description: "Speech recognition and synthesis for calls and voice assistants.",
      },
      omni: {
        title: "Omni-channels",
        description: "Chat, messengers, email — unified dialogue context.",
      },
      reasoning: {
        title: "Reasoning",
        description: "Multi-step analysis and decision making.",
      },
      integrations: {
        title: "Integrations",
        description: "APIs and connectors to popular business systems.",
      },
      rag: {
        title: "RAG",
        description: "Retrieval-Augmented Generation for accurate answers.",
      },
      deployment: {
        title: "Deployment",
        description: "On-premise, cloud or hybrid.",
      },
    },
    caseStudies: {
      title: "Case Studies & Results",
      subtitle: "Real impact from enterprise deployments",
      nps: {
        metric: "+32",
        label: "NPS Increase",
        description: "Improved customer satisfaction through fast responses.",
        company: "Major Bank",
      },
      automation: {
        metric: "80%",
        label: "Automation",
        description: "Share of requests resolved without human agents.",
        company: "Telecom",
      },
      cost: {
        metric: "-40%",
        label: "Cost Reduction",
        description: "Optimized support and infrastructure spend.",
        company: "Retail",
      },
      response: {
        metric: "<5s",
        label: "Response Time",
        description: "Average time for customer to get an answer.",
        company: "Insurance Company",
      },
    },
    roadmap: {
      title: "Roadmap",
      subtitle: "Implementation stages from pilot to scale",
      step1: {
        duration: "2–4 weeks",
        title: "Pilot",
        description: "Deploy on one scenario, evaluate results.",
      },
      step2: {
        duration: "1–2 months",
        title: "Training",
        description: "Connect knowledge, fine-tuning, system integration.",
      },
      step3: {
        duration: "3+ months",
        title: "Scale",
        description: "Expand to new processes and departments.",
      },
    },
    team: {
      title: "Our Team",
      subtitle: "Experience in AI, enterprise systems and corporate projects",
      specialists: {
        value: "50+",
        label: "Specialists",
        description: "Engineers, linguists, domain experts.",
      },
      experience: {
        value: "5+ years",
        label: "Experience",
        description: "In AI development and deployment.",
      },
      deployments: {
        value: "30+",
        label: "Deployments",
        description: "Successful projects at large companies.",
      },
    },
    cta: {
      title: "Ready to discuss your project?",
      subtitle: "Book a demo or chat with our agent",
      bookDemo: "Book a demo",
      talkToAgent: "Talk to agent",
    },
    footer: {
      description: "Enterprise AI platform for automating and enhancing business processes.",
      product: "Product",
      company: "Company",
      resources: "Resources",
      legal: "Legal",
      copyright: "dzen.ai. All rights reserved.",
      platform: "Platform",
      solutions: "Solutions",
      pricing: "Pricing",
      documentation: "Documentation",
      about: "About",
      caseStudies: "Case Studies",
      careers: "Careers",
      contact: "Contact",
      blog: "Blog",
      apiReference: "API",
      support: "Support",
      status: "Status",
      privacy: "Privacy",
      terms: "Terms",
      security: "Security",
    },
  }),
}

type LanguageContextValue = {
  language: Language
  setLanguage: (lang: Language) => void
  t: (key: string) => string
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [language, setLanguage] = useState<Language>("ru")

  const t = useCallback(
    (key: string): string => {
      const langMap = translations[language]
      return langMap[key] ?? translations.en[key] ?? key
    },
    [language]
  )

  return (
    <LanguageContext.Provider value={{ language, setLanguage, t }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage(): LanguageContextValue {
  const ctx = useContext(LanguageContext)
  if (!ctx) {
    throw new Error("useLanguage must be used within LanguageProvider")
  }
  return ctx
}
