/** Единые кейсы для витрины: все строки локализуются через languageContent.ru / languageContent.en */

export type Locale = "ru" | "en";

export type CaseMetricCard = {
  value: string;
  label: string;
  detail?: string;
};

export type AgentLayer = {
  title: string;
  body: string;
};

/** Плоский текстовый слой языка без дублирования JSX */
export type CaseLanguageLayer = {
  title: string;
  subtitle: string;
  /** 1–2 строки на закрытой карточке */
  cardDescription: string;
  /** Коротко в раскрытом блоке «позиционирование» */
  positioning: string;
  /** Развернутое описание */
  description: string;
  /** Что делает система — буллеты */
  capabilities: string[];
  /** Архитектура / цепочка агентов */
  agents: AgentLayer[];
  outcomes: string[];
  /** Ровно 3 блока для карточки */
  previewMetrics: [CaseMetricCard, CaseMetricCard, CaseMetricCard];
  /** Полный список для раскрытого режима */
  metrics: CaseMetricCard[];
  mediaAlt: string;
};

export type CaseMediaTreatment = "fintech_signal" | "glass_avatar" | "industrial_mesh" | "floating_product";

export type CaseStudyId = "idram" | "inspectra" | "metallica" | "agronomist";

export type UnifiedCaseStudy = {
  id: CaseStudyId;
  accentColor: string;
  /** дополнительный оттенок для градиента / свечения */
  accentSecondary?: string;
  mediaTreatment: CaseMediaTreatment;
  /** имя файла в /local */
  mediaFile: string;
  languageContent: Record<Locale, CaseLanguageLayer>;
};

function mediaUrl(file: string) {
  return `/local/${encodeURIComponent(file)}`;
}

export function getCaseMediaSrc(study: UnifiedCaseStudy) {
  return mediaUrl(study.mediaFile);
}

export function localizeCaseStudy(study: UnifiedCaseStudy, locale: Locale): CaseLanguageLayer {
  return study.languageContent[locale];
}

export const UNIFIED_CASE_STUDIES: UnifiedCaseStudy[] = [
  {
    id: "idram",
    accentColor: "#ea580c",
    accentSecondary: "#fbbf24",
    mediaTreatment: "fintech_signal",
    mediaFile: "IdramLogo.png",
    languageContent: {
      ru: {
        title: "Idram",
        subtitle: "Голосовой контакт-центр и real-time связь в финтехе",
        cardDescription:
          "Мультиягентная линия для инцидентов: армянский язык, мгновенные статус-линии голосом и контролируемая эскалация.",
        positioning:
          "Национальный финтех держит миллионы пользователей в курсе сбоев: три агента ведут инцидент от входящего звонка до авто‑outbound после восстановления сервисов.",
        description:
          "Один из первых масштабных разговорных AI-деплойментов на армянском: операторская панель запускает сценарии при массовых сбоях, NLU-классификатор стабилизирует понимание на фоне слабого ASR.",
        capabilities: [
          "Ручной запуск голосовых сценариев при падении множества сервисов",
          "Потоковые обновления по голосу и чату без «стены текста»",
          "Прозрачные SLA для подписчиков кошелька и платежей",
          "Снижение нагрузки на живую линию в пики инцидентов",
        ],
        agents: [
          {
            title: "Agent 1 — входящий контур",
            body: "Входящие звонки: оповещение о сбоях и сервисах, объяснение проблемы, актуальный статус в реальном времени.",
          },
          {
            title: "Agent 2 — инцидентный журнал",
            body: "Логирует обращения в период инцидента, структурирует намерение и временные метки для последующего анализа.",
          },
          {
            title: "Agent 3 — исходящий контур",
            body: "Авто-обзвон после восстановления сервисов: закрывает петлю доверия и снимает нагрузку с операторов.",
          },
        ],
        outcomes: [
          "Прозрачные коммуникации при сбоях платежной инфраструктуры",
          "Человеческий контроль сохранён, темп коммуникации держат агенты",
          "Референс модели AI-first регфинтеха для региона",
        ],
        previewMetrics: [
          { value: "> 80%", label: "автоматизация" },
          { value: "Live", label: "real-time SLA" },
          { value: "100%", label: "outbound после восстановления" },
        ],
        metrics: [
          {
            value: "> 80%",
            label: "автоматизация",
            detail: "доля автоматической обработки в пики инцидентов без передачи на оператора",
          },
          { value: "< 2 с", label: "реакция", detail: "медиана ответа голосового ассистента в горячее окно",
          },
          { value: "100%", label: "post-incident outbound", detail: "автоверифицированное оповещение после green status" },
          { value: "WER-safe NLU", label: "голос под стрессом", detail: "классификатор над слабым ASR сохраняет интент" },
        ],
        mediaAlt: "Брендинг сервиса Idram на тёмном фоне",
      },
      en: {
        title: "Idram",
        subtitle: "Voice contact center continuity for Armenia’s fintech stack",
        cardDescription:
          "Multi-agent first line tuned for outages: Armenian conversational AI with live narration and deterministic escalation ladders.",
        positioning:
          "Keeps subscribers informed across wallet + payments rails—from inbound assurance through automated outbound once services stabilize.",
        description:
          "Flagship conversational deployment layered with proprietary NLU to survive weak ASR, plus banker mission control for scripted bursts.",
        capabilities: [
          "Operator-triggered voice bursts whenever parallel services degrade",
          "Realtime voice/chat storytelling instead of brittle FAQ walls",
          "Transparent SLAs surfaced as empathetic conversational beats",
          "Elastic load shedding on humans during cascading incidents",
        ],
        agents: [
          {
            title: "Agent 1 — inbound voice",
            body: "Answers inbound spikes, contextualizes disruptions, mirrors live SLA data with empathic narration.",
          },
          {
            title: "Agent 2 — incident ledger",
            body: "Captures intents, timelines, channels for every outage interaction without losing nuance.",
          },
          {
            title: "Agent 3 — recovery outbound",
            body: "Auto-dials subscribers post-recovery, closing loops so humans focus on supervising strategy.",
          },
        ],
        outcomes: [
          "Radical CX transparency whenever payment rails jitter",
          "Humans stay in command while agents steward cadence",
          "Blueprint for conversational fintech fleets in Armenian",
        ],
        previewMetrics: [
          { value: "> 80%", label: "automation" },
          { value: "Live", label: "real-time SLA" },
          { value: "100%", label: "recovery calls" },
        ],
        metrics: [
          {
            value: "> 80%",
            label: "automation depth",
            detail: "Share of intents resolved agent-side during outage peaks.",
          },
          { value: "< 2 s", label: "response feel", detail: "Perceived conversational latency envelope on hot paths." },
          { value: "100%", label: "outbound fidelity", detail: "Coverage of scripted recovery confirmations post-service." },
          { value: "WER-safe NLU", label: "voice resilience", detail: "Dedicated classifier insulating weak ASR from dialogue drift." },
        ],
        mediaAlt: "Idram brand emblem on noir stage",
      },
    },
  },
  {
    id: "inspectra",
    accentColor: "#5b73ff",
    accentSecondary: "#8b5cf6",
    mediaTreatment: "glass_avatar",
    mediaFile: "Inspectra.jpg",
    languageContent: {
      ru: {
        title: "Inspectra",
        subtitle: "Городской AI для комплаенса, контроля и прозрачности",
        cardDescription:
          "Аватар-навигатор по регуляторике для бизнеса и граждан: холодное стекло, строгий ритм и единое окно статусов.",
        positioning:
          "Мультиягентная оболочка департамента контроля крупнейшей европейской столицы: консультации, режим проверок, инциденты и синхронизация ведомств.",
        description:
          "Smart KB консолидирует нормативы и процедуры; диалог и аналитика помогают бизнесу и жителям получать понятные ответы без бюрократических стен текста.",
        capabilities: [
          "Поиск и выдача регуляторной информации под контекст пользователя",
          "Поддержка решений инспекторов и смежных подразделений",
          "Статусы проверок и инцидентов в едином потоке",
          "Прозрачная коммуникация между ведомствами, SME и населением",
        ],
        agents: [
          {
            title: "Слой 1 — Regulatory intelligence",
            body: "Поиск и объяснение нормативных требований в формате живого диалога.",
          },
          {
            title: "Слой 2 — Decision copilot",
            body: "Поддержка управленческих и инспекторских решений на базе смарт-базы процедур.",
          },
          {
            title: "Слой 3 — Incident surface",
            body: "Статусы проверок и инцидентов синхронизируются между департаментами и аудиторией.",
          },
          {
            title: "Слой 4 — Transparency mesh",
            body: "Прозрачные каналы voice/chat/web для людей и бизнеса без потери SLA.",
          },
        ],
        outcomes: [
          "Рост восприятия сервиса и доверия к государственному AI-контуру",
          "Снижение стоимости контактов через автономность потоков",
          "Стандартизированный playbook для смарт-сити платформ",
        ],
        previewMetrics: [
          { value: "< 2 сек", label: "латентность" },
          { value: "> 85%", label: "точность" },
          { value: "> 80%", label: "автономность" },
        ],
        metrics: [
          {
            value: "< 2 с",
            label: "ответ ассистента",
            detail: "медианная скорость реакции в горячих сценариях",
          },
          { value: "> 85%", label: "аккуратность ответов", detail: "валидация через QA и экспертные ревью" },
          {
            value: "+35%",
            label: "NPS vs база",
            detail: "рост удовлетворённости восприятия сервиса",
          },
          { value: "−50%", label: "cost per contact", detail: "снижение стоимости контакта к legacy" },
          { value: "> 80%", label: "вовлечение", detail: "повторные обращения в окне наблюдения" },
          { value: "95%", label: "инциденты с SLA", detail: "доля обращений с фиксируемыми апдейтами статусов" },
        ],
        mediaAlt: "Цифровой аватар Inspectra для контуров комплаенса",
      },
      en: {
        title: "Inspectra",
        subtitle: "Civic-grade compliance & control conversational fabric",
        cardDescription:
          "Avatar-guided regulatory intelligence connecting agencies, SMEs, and residents behind glassy noir UI.",
        positioning:
          "Operational AI for Europe’s mega-capital control department—inspection regimes, statutes, incidents, fused Smart KB.",
        description:
          "Retrieval plus conversational scaffolding keeps answers crisp; analytics aligns departments while citizens consume transparent timelines.",
        capabilities: [
          "Regulatory corpus discovery tuned to conversational context",
          "Decision enablement copilots for inspectors and SMEs",
          "Inspection + incident timelines unified for every audience",
          "Transparent communications bridging agencies, commerce, civic life",
        ],
        agents: [
          {
            title: "Lane 1 — Regulatory intelligence",
            body: "Finds statutes, reframes jargon into empathic conversational guidance.",
          },
          {
            title: "Lane 2 — Decision copilot",
            body: "Aligns supervisory decisions against procedural anchors from the corpus.",
          },
          {
            title: "Lane 3 — Incident surface",
            body: "Syncs statuses across departments with explainable deltas.",
          },
          {
            title: "Lane 4 — Transparency mesh",
            body: "Extends reassurance through omnichannel narration without SLA drift.",
          },
        ],
        outcomes: [
          "Trust loops heal between municipalities, SMEs, enterprises",
          "Automation absorbs repetitive desk load while experts supervise",
          "Repeatable playbook for sovereign smart-city AI overlays",
        ],
        previewMetrics: [
          { value: "< 2 s", label: "latency" },
          { value: "> 85%", label: "precision" },
          { value: "> 80%", label: "autonomy" },
        ],
        metrics: [
          {
            value: "< 2 s",
            label: "assistant latency",
            detail: "Median conversational reaction under compliance spikes.",
          },
          { value: "> 85%", label: "answer fidelity", detail: "QA-reviewed accuracy on regulated intents." },
          { value: "+35%", label: "NPS lift", detail: "Service perception uplift over historical baseline." },
          { value: "−50%", label: "CPC decline", detail: "Cost-per-contact erosion vs analog workflows." },
          { value: "> 80%", label: "engagement", detail: "Repeat interaction cohort health." },
          { value: "95%", label: "tracked incidents", detail: "Share logged with SLA-grade transparency." },
        ],
        mediaAlt: "Inspectra digital avatar embodying civic compliance UX",
      },
    },
  },
  {
    id: "metallica",
    accentColor: "#9ca3af",
    accentSecondary: "#eab308",
    mediaTreatment: "industrial_mesh",
    mediaFile: "Metallica.png",
    languageContent: {
      ru: {
        title: "Metallica",
        subtitle: "Промышленный цифровой двойник знаний",
        cardDescription:
          "Единая тёмная сцена поверх смарт-базы каталогов и регламентов: решения без лишних переходов по PDF.",
        positioning:
          "Разрозненные знания предприятия сведены в одну промышленную память — с валидацией, экспертными рекомендациями и обучением сотрудников.",
        description:
          "Команды на полу и в штабе получают естественно-языковой доступ к продуктам, процедурам и проверкам, ускоряя time-to-decision без выгорания экспертов.",
        capabilities: [
          "Единая база знаний промышленного контура",
          "Поиск по продуктовому каталогу и техническим пакетам",
          "Валидация операционных и технических решений",
          "Экспертные рекомендации с опорой на регламенты",
          "Обучение сотрудников и снижение ошибок в эксплуатации",
        ],
        agents: [
          { title: "Узел 1 — Semantic catalog", body: "Семантический поиск по SKU, BOM и сопроводительной документации." },
          { title: "Узел 2 — Policy mesh", body: "Стягивает регламенты, чеклисты и локальные нормативные акты." },
          { title: "Узел 3 — Validation core", body: "Проверяет решения против KPI-боксов безопасности и качества." },
          { title: "Узел 4 — Expert relay", body: "Подсказывает сценарии эскалации и комплектаций для инженеров." },
          { title: "Узел 5 — Training loop", body: "Поддерживает онбординг и снижает возвраты после обучения." },
        ],
        outcomes: [
          "Экспертиза масштабируется без линейного роста поддержки",
          "Снижена фрагментация между цехами и корпоративным офисом",
          "Подготовка к расширению SKU без простоя знаний",
        ],
        previewMetrics: [
          { value: "3×", label: "быстрее решения" },
          { value: "82%", label: "подтверждённые решения" },
          { value: "> 70%", label: "покрытие сценариев" },
        ],
        metrics: [
          {
            value: "82%",
            label: "без экспертной пересборки",
            detail: "доля решений, прошедших автоматическую валидацию",
          },
          { value: "3×", label: "time-to-decision", detail: "ускорение против legacy комиссий и рассылок" },
          { value: "−40%", label: "стоимость консультаций", detail: "снижение внутреннего времени поддержки экспертами" },
          { value: "> 70%", label: "каталог охвата", detail: "типовые операционные сценарии закрывает база знаний" },
          {
            value: "−80%",
            label: "ошибки после обучения",
            detail: "контур обучения снижает логистические промахи",
          },
          { value: "> 90%", label: "доверие SME", detail: "доля подтверждённой экспертизой качества подсказок" },
        ],
        mediaAlt: "Промышленный интерфейс цифрового двойника знаний",
      },
      en: {
        title: "Metallica",
        subtitle: "Industrial knowledge twin atop enterprise Smart KB",
        cardDescription:
          "Graphite stage with KPI-grade glow—every asset framed like mission control, not disparate screenshots.",
        positioning:
          "Unifies dispersed plant dossiers into conversational intelligence with validations, SKU logic, onboarding copilots.",
        description:
          "Operators converse with BOMs + procedures concurrently, shrinking committee latency while sparing scarce SMEs from FAQ loops.",
        capabilities: [
          "Single-pane industrial memory mesh",
          "Semantic catalog traversal for SKU + BOM families",
          "Operational + technical decision validation ladders",
          "Expert-grade recommendations tethered to policy",
          "Always-on workforce training reinforcement",
        ],
        agents: [
          { title: "Node 1 — Semantic catalog", body: "Vector + lexical retrieval tuned for mill jargon." },
          { title: "Node 2 — Policy mesh", body: "Harvests dossiers + safety overlays into one reasoning slab." },
          { title: "Node 3 — Validation core", body: "Ensures KPI envelopes before executions roll to floor." },
          { title: "Node 4 — Expert relay", body: "Bundles escalation kits for engineers juggling complexity." },
          { title: "Node 5 — Training loop", body: "Shrinks onboarding defects + mis-shipping windows." },
        ],
        outcomes: [
          "Institutional IQ becomes kinetic advantage",
          "Field + HQ converge on authoritative answers",
          "Scale breadth of SKUs without proportional support hiring",
        ],
        previewMetrics: [
          { value: "3×", label: "faster commits" },
          { value: "82%", label: "auto-validated" },
          { value: "> 70%", label: "coverage" },
        ],
        metrics: [
          {
            value: "82%",
            label: "validations untouched",
            detail: "Plans passing automated governance without SME rewrites.",
          },
          {
            value: "3×",
            label: "decision accel",
            detail: "Committee shrink vs legacy analogue workflows.",
          },
          {
            value: "−40%",
            label: "consult cost",
            detail: "Operational savings on internal escalation minutes.",
          },
          { value: "> 70%", label: "playbook breadth", detail: "Recurring ops paths resolved self-serve." },
          { value: "−80%", label: "training defects", detail: "Post-training mis-shipping suppression." },
          { value: "> 90%", label: "expert QA pass", detail: "Audited responses clearing SME checkpoints." },
        ],
        mediaAlt: "Industrial knowledge cockpit visual",
      },
    },
  },
  {
    id: "agronomist",
    accentColor: "#16a34a",
    accentSecondary: "#eab308",
    mediaTreatment: "floating_product",
    mediaFile: "Digital Twin of Agronomist.png",
    languageContent: {
      ru: {
        title: "Иван Полевой · Agronomist",
        subtitle: "Полевая AI-платформа: CV, голос и калькуляторы удобрений",
        cardDescription:
          "Интерфейс и ассистент в одном кадре: плавающий product preview поверх смарт-базы агропредприятия.",
        positioning:
          "Цифровой двойник агронома соединяет регион, тип почвы, культуру и мультимодальное общение для полевых бригад и штаба.",
        description:
          "Голос, чат, изображения и графики сходятся в одном conversational слое — от калькуляторов питательных смесей до CV на листьях под стрессом сезона.",
        capabilities: [
          "Калькулятор удобрений с учётом региона, почвы и культуры",
          "Аналитика территории по спутниковым и полевым сигналам",
          "Компьютерное зрение для дефицитов элементов и здоровья растений",
          "Генерация агрономических рекомендаций поверх смарт-базы",
          "Мультимодальная поддержка (текст, изображение, голос)",
        ],
        agents: [
          {
            title: "Конвейер 1 — Полевые сигналы",
            body: "Собирает изображение, локальную телеметрию и климатические намёки участка.",
          },
          {
            title: "Конвейер 2 — Nutrition math",
            body: "Строит сценарии подкормок и совместимости с ограничениями региона.",
          },
          {
            title: "Конвейер 3 — Vision QA",
            body: "Подсвечивает стресс-отпечатки листвы и недостачи микроэлементов.",
          },
          {
            title: "Конвейер 4 — Expert voice",
            body: "Синхронизирует рекомендации с живыми экспертами и регламентами.",
          },
          {
            title: "Конвейер 5 — Multimodal desk",
            body: "Стабилизирует UX для бригад — от фото почвы до push-ответов голосом.",
          },
        ],
        outcomes: [
          "Урожайность держится за счёт ранней диагностики стресса растений",
          "Логистика удобрений и складов становится управляемой в пик сезона",
          "Дефицит агрономов смягчается conversational слоем масштабируемой экспертизы",
        ],
        previewMetrics: [
          { value: "3×", label: "скорость консультаций" },
          { value: "> 90%", label: "валидация экспертами" },
          { value: "> 80%", label: "удержание операторов" },
        ],
        metrics: [
          {
            value: "> 80%",
            label: "рекомендации без правок",
            detail: "доля советов принятых без цикла эксперта в пик сезона",
          },
          {
            value: "3×",
            label: "ускорение decisioning",
            detail: "соотношение времени против классического агро-ЦКК",
          },
          { value: "> 65%", label: "покрытие playbook", detail: "частые сценарии закрывает база кейсов" },
          { value: "> 90%", label: "экспертный QA", detail: "соответствие рекомендаций полевым стандартам" },
          {
            value: "> 70%",
            label: "MAU активности",
            detail: "вовлечённость ключевых подразделений в пилоте",
          },
          {
            value: "> 80%",
            label: "повтор сезон-сезон",
            detail: "удержание сценариев после первого производственного цикла",
          },
        ],
        mediaAlt: "Интерфейс цифрового агро-ассистента Agronomist",
      },
      en: {
        title: "Field Copilot · Agronomist",
        subtitle: "Multimodal agronomy cockpit with fertilizer intelligence",
        cardDescription:
          "Floating SaaS-inspired preview keeps UI shots cinematic—never raw screenshots pasted onto the page.",
        positioning:
          "Twin stack unifies soil taxonomy, cropping strategy, conversational agents, CV signals for distributed ag enterprises.",
        description:
          "Voice + imagery + calculators ride one orchestration slab so scouts never break flow between clipboards & analytics.",
        capabilities: [
          "Fertilizer intelligence bound to region/soil taxonomy/crop genotype",
          "Territorial analytics blending satellite cues + scouting intel",
          "Computer vision diagnosing nutrient stress & canopy health",
          "Agronomic recommendations grounded by Smart KB + SME guardrails",
          "Multimodal orchestration bridging text/image/voice",
        ],
        agents: [
          {
            title: "Stream 1 — Field sensing",
            body: "Fuses scouting imagery with micro-climate heuristics anchored to parcels.",
          },
          {
            title: "Stream 2 — Nutrition math",
            body: "Builds fertilizer recipes respecting regional bans + soil chemistry.",
          },
          {
            title: "Stream 3 — Vision QA",
            body: "Flags canopy stress fingerprints & micronutrient starvation early.",
          },
          {
            title: "Stream 4 — Expert voice",
            body: "Aligns AI answers with agronomists, cooperatives, compliance officers.",
          },
          {
            title: "Stream 5 — Multimodal desk",
            body: "Stabilizes mobile UX—from soil selfies to conversational push guidance.",
          },
        ],
        outcomes: [
          "Yield resilience boosted by preemptive physiology alerts",
          "Fertilizer + warehouse logistics tame harvest spikes",
          "Scalable agronomic cognition without multiplying headcount",
        ],
        previewMetrics: [
          { value: "3×", label: "faster agronomy loops" },
          { value: "> 90%", label: "SME audited" },
          { value: "> 80%", label: "operator WAU" },
        ],
        metrics: [
          {
            value: "> 80%",
            label: "advice accepted",
            detail: "Share of prescriptions accepted untouched during peaks.",
          },
          {
            value: "3×",
            label: "consult accel",
            detail: "Throughput delta vs analogue agronomic committee.",
          },
          { value: "> 65%", label: "playbook depth", detail: "Frequent agronomic intents covered offline." },
          { value: "> 90%", label: "QA coverage", detail: "Recommendations adhering to agronomy SME checkpoints." },
          { value: "> 70%", label: "WAU fidelity", detail: "Active agronomy squads sustaining monthly rituals." },
          { value: "> 80%", label: "repeat seasons", detail: "Post-pilot adherence across harvest cycles." },
        ],
        mediaAlt: "Agronomist digital twin interface framed as cinematic product preview",
      },
    },
  },
];
