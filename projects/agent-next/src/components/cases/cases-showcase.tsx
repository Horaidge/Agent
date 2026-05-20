"use client";

import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import Image from "next/image";
import { useEffect, useState, type CSSProperties } from "react";

import type { AgentLayer, CaseStudyId, Locale, UnifiedCaseStudy } from "@/content/enterprise-cases";
import { localizeCaseStudy, UNIFIED_CASE_STUDIES, getCaseMediaSrc } from "@/content/enterprise-cases";
import { CaseLocaleProvider, useCaseLocale } from "@/context/case-locale-context";

const SOFT: [number, number, number, number] = [0.22, 1, 0.36, 1];

const SECTION_LABEL: Record<
  "positioning" | "description" | "capabilities" | "architecture" | "outcomes" | "metrics",
  Record<Locale, string>
> = {
  positioning: { ru: "Позиционирование", en: "Positioning" },
  description: { ru: "Описание", en: "Description" },
  capabilities: { ru: "Что делает система", en: "What the platform does" },
  architecture: { ru: "Архитектура агентов", en: "Agent architecture" },
  outcomes: { ru: "Ключевые результаты", en: "Key outcomes" },
  metrics: { ru: "Ключевые метрики", en: "Key metrics" },
};

const UI_LABEL: Record<
  "eyebrow" | "headline" | "sub" | "openCase" | "closeCase",
  Record<Locale, string>
> = {
  eyebrow: { ru: "Интерактивная витрина", en: "Interactive showcase" },
  headline: { ru: "Единые сцены разных типов медиа", en: "One frame for every media type" },
  sub: {
    ru: "Логотипы, аватары, промышленные интерфейсы и продуктовые экраны в одном визуальном языке: тёмное стекло, акцентный свет и спокойная механика.",
    en: "Logos, avatars, industrial decks, UX captures—mounted in the same glass stage, halo, and choreography.",
  },
  openCase: { ru: "Открыть кейс", en: "Open case" },
  closeCase: { ru: "Свернуть", en: "Close" },
};

function pick<T extends Record<Locale, string>>(b: T, locale: Locale) {
  return b[locale];
}

function ambientAccent(id: CaseStudyId | "ambient"): string {
  switch (id) {
    case "idram":
      return "#ea580c";
    case "inspectra":
      return "#5b73ff";
    case "metallica":
      return "#9ca3af";
    case "agronomist":
      return "#16a34a";
    default:
      return "#e7c59a";
  }
}

/** Оранжевая «линия связи» под логотипом Idram */
function VoiceLinkSketch({ hue, boosted }: { hue: string; boosted: boolean }) {
  const reduce = useReducedMotion();
  return (
    <div aria-hidden className="absolute inset-x-0 bottom-0 flex h-[40%] items-end justify-center gap-[3px] pb-11 opacity-95" style={{ color: hue }}>
      {Array.from({ length: 40 }).map((_, i) => (
        <motion.span
          key={i}
          className="w-[4px] max-w-[5px] flex-1 origin-bottom rounded-full bg-current"
          style={{ height: 42 + ((i * 61) % 26) }}
          animate={
            reduce || !boosted
              ? { scaleY: 0.6 }
              : { scaleY: [0.42, 0.94 + (i % 5) * 0.045, 0.58] }
          }
          transition={{ repeat: reduce ? 0 : Infinity, duration: 4.4 + i * 0.04, ease: "easeInOut" }}
        />
      ))}
    </div>
  );
}

function LatticeOverlay({ color }: { color: string }) {
  const stripe = `${color}1c`;
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute inset-0 opacity-[0.65] mix-blend-soft-light"
      style={{
        backgroundImage: `linear-gradient(${stripe} 1px, transparent 1px), linear-gradient(90deg, ${stripe} 1px, transparent 1px)`,
        backgroundSize: "46px 46px",
        maskImage: "radial-gradient(ellipse at 52% 40%,rgba(0,0,0,1),transparent 74%)",
      } as CSSProperties}
    />
  );
}

/** Единые медиа-сцены по типам */
function CaseStudyMediaStage({
  study,
  locale,
  mode,
  motionBoost,
}: {
  study: UnifiedCaseStudy;
  locale: Locale;
  mode: "card" | "drawer";
  motionBoost: boolean;
}) {
  const L = localizeCaseStudy(study, locale);
  const src = getCaseMediaSrc(study);
  const accent = study.accentColor;
  const halo = study.accentSecondary ?? accent;
  const reduce = useReducedMotion();
  const hClass =
    mode === "card" ? "relative aspect-[21/11] min-h-[200px]" : "relative min-h-[clamp(268px,40vh,480px)] w-full";

  const baseBackdrop = (
    <>
      <div className="absolute inset-0 bg-gradient-to-br from-black via-[#080a12] to-[#030409]" />
      <div
        className="absolute inset-0 opacity-96"
        style={{
          background: `radial-gradient(ellipse 70% 72% at 50% 88%,color-mix(in_oklab,${accent}70,transparent),transparent 70%)`,
        }}
      />
    </>
  );

  const imgBoost = motionBoost && !reduce;

  switch (study.mediaTreatment) {
    case "fintech_signal":
      return (
        <div className={`${hClass} overflow-hidden`}>
          {baseBackdrop}
          <VoiceLinkSketch hue={halo} boosted={motionBoost} />
          <div className="pointer-events-none absolute inset-[34%] rounded-full opacity-[0.9] blur-[120px]"
            style={{ background: `radial-gradient(circle,color-mix(in_oklab,${halo}80,transparent),transparent)` }}
          />
          <motion.div className="relative z-[6] flex h-full items-center justify-center px-14 py-16">
            <motion.div animate={imgBoost ? { y: [-2, 2, -1] } : {}} transition={{ repeat: Infinity, duration: 8 }}>
              <Image
                src={src}
                alt={L.mediaAlt}
                width={640}
                height={320}
                className="h-auto max-h-[158px] w-auto max-w-[min(296px,70vw)] object-contain saturate-[1.12] drop-shadow-[0_30px_80px_rgba(0,0,0,0.88)]"
                priority={study.id === "idram"}
              />
            </motion.div>
          </motion.div>
          <motion.div animate={motionBoost ? { rotate: [-0.4, 0.35] } : {}} transition={{ repeat: Infinity, duration: 26, ease: "easeInOut" }}
            className="pointer-events-none absolute inset-[-8%]"
            style={{ background: `linear-gradient(120deg,color-mix(in_oklab,${halo}35,transparent),transparent)` }}
          />
        </div>
      );
    case "glass_avatar":
      return (
        <div className={`${hClass} overflow-hidden`}>
          {baseBackdrop}
          <LatticeOverlay color={accent} />
          <div className="absolute inset-0 opacity-[0.35]">
            <Image fill src={src} alt="" className="scale-115 object-cover blur-3xl" sizes="82vw" />
          </div>
          <div className="relative z-[5] flex h-full items-center justify-center px-8 py-12">
            <motion.div animate={imgBoost ? { scale: [1, 1.042, 1.016] } : {}} transition={{ repeat: Infinity, duration: 10.5 }}>
              <div
                className="relative overflow-hidden rounded-[2.05rem] border border-white/18 shadow-[0_54px_120px_rgba(4,14,62,0.78),inset_0_1px_0_rgba(255,255,255,0.28)] backdrop-blur-2xl"
                style={{
                  background: `linear-gradient(154deg,rgba(255,255,255,0.08),rgba(8,10,42,0.55)),
                    radial-gradient(120% 80% at 50% -4%,color-mix(in_oklab,${accent}66,transparent),transparent 60%)`,
                }}
              >
                <div className="relative aspect-square w-[min(290px,80vw)] sm:w-[clamp(296px,30vw,320px)]">
                  <motion.div animate={imgBoost ? { scale: [1, 1.06, 1.03] } : {}} transition={{ repeat: Infinity, duration: 12 }} className="absolute inset-[0]">
                    <Image src={src} alt={L.mediaAlt} fill sizes="340px" className="object-cover" />
                  </motion.div>
                  <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-black/8 via-transparent to-black/74" />
                </div>
                <motion.div animate={motionBoost ? { opacity: [0.6, 0.9, 0.66] } : {}} transition={{ repeat: Infinity, duration: 6 }}
                  className="pointer-events-none absolute inset-[0]"
                  style={{ boxShadow: `inset 0 0 0 1px color-mix(in_oklab,${accent}94,transparent)` }}
                />
              </div>
            </motion.div>
          </div>
        </div>
      );
    case "industrial_mesh":
      return (
        <div className={`${hClass} overflow-hidden`}>
          {baseBackdrop}
          <LatticeOverlay color={accent} />
          <motion.div
            animate={imgBoost ? { scale: [1.05, 1.098, 1.068] } : {}}
            transition={{ repeat: Infinity, duration: 18 }}
            className="absolute inset-[0]"
          >
            <Image fill src={src} alt={L.mediaAlt} className="object-cover opacity-[0.9]" sizes="(min-width:1024px)800px,100vw" />
          </motion.div>
          <div className="absolute inset-0 z-[8] bg-gradient-to-t from-[#06070f] via-[#06070f]/74 to-transparent" />
          <div className="absolute inset-[0] z-[9]" style={{
            boxShadow: `inset 0 0 90px rgba(0,0,0,0.78), inset 0 0 0 1px color-mix(in_oklab,${halo}32,transparent)`,
          }} />
        </div>
      );
    case "floating_product":
    default:
      return (
        <div className={`${hClass} overflow-hidden`}>
          {baseBackdrop}
          <LatticeOverlay color={accent} />
          <div className="relative z-[4] flex h-full items-center justify-center px-9 py-10" style={{ perspective: "980px" }}>
            <motion.div animate={imgBoost ? { rotateY: [-1.1, 0.9], y: [-3, 2] } : { rotateY: 0 }} transition={{ repeat: Infinity, duration: 14 }}>
              <div
                className="relative w-[clamp(294px,86vw,520px)] max-w-full overflow-hidden rounded-[1.74rem] border border-white/[0.14] shadow-[0_44px_100px_rgba(0,0,0,0.72)]"
                style={{
                  transform: "rotateX(6deg) rotateY(-5deg)",
                  background: `linear-gradient(154deg,color-mix(in_oklab,${accent}42,transparent),rgba(2,8,26,0.78))`,
                }}
              >
                <Image src={src} alt={L.mediaAlt} width={1100} height={720} className="block h-auto w-full object-cover" sizes="560px" />
                <motion.div animate={motionBoost ? { opacity: [0.5, 0.9, 0.6] } : {}} transition={{ repeat: Infinity, duration: 5.8 }} className="pointer-events-none absolute inset-0" style={{
                  boxShadow: `inset 0 0 0 1px color-mix(in_oklab,${accent}ac,transparent)`,
                }} />
              </div>
            </motion.div>
          </div>
          <div className="pointer-events-none absolute inset-0 z-[10] bg-gradient-to-t from-[#050609] via-transparent to-black/72" />
        </div>
      );
  }
}

function SectionBanner({ sid }: { sid: keyof typeof SECTION_LABEL }) {
  const { locale } = useCaseLocale();
  return <p className="mono mb-3 text-[0.64rem] uppercase tracking-[0.32em] text-[color:rgb(255_255_255_/0.45)]">{SECTION_LABEL[sid][locale]}</p>;
}

function MetricStrip({ trio, accent }: { trio: { value: string; label: string }[]; accent: string }) {
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
      {trio.map((row) => (
        <motion.div
          layout
          key={row.label + row.value}
          whileHover={{ y: -2 }}
          transition={{ duration: 0.35, ease: SOFT }}
          className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[rgba(10,11,21,0.88)] px-4 py-[0.94rem]"
          style={{
            boxShadow: `inset 0 1px 0 rgba(255,255,255,0.05), inset 0 0 42px ${accent}29`,
          }}
        >
          <span className="block text-[1.2rem] font-semibold tracking-tight text-[var(--color-polar-white)]">{row.value}</span>
          <span className="mt-2 block text-[0.64rem] uppercase leading-snug tracking-[0.16em] text-[color:rgb(255_255_255_/0.52)]">
            {row.label}
          </span>
        </motion.div>
      ))}
    </div>
  );
}

function AgentRibbon({ accent, layers }: { accent: string; layers: AgentLayer[] }) {
  return (
    <div className="flex gap-4 overflow-x-auto pb-4 sm:snap-none md:flex-wrap">
      {layers.map((layer, idx) => (
        <div key={layer.title} className="flex items-stretch gap-4 md:gap-6">
          <motion.div initial={{ opacity: 0.6, scale: 0.98 }} whileInView={{ opacity: 1, scale: 1 }} viewport={{ once: true, margin: "-12%" }} transition={{ duration: 0.6, ease: SOFT }} className="min-h-[154px] w-[clamp(268px,_78vw,_320px)] flex-shrink-0 rounded-[1.62rem] border border-white/[0.09] bg-white/[0.03] px-5 py-[1.06rem] shadow-[inset_0_1px_0_rgba(255,255,255,0.18)] backdrop-blur-xl md:flex-1 md:min-h-0">
            <span className="mono text-[0.58rem] uppercase tracking-[0.28em]" style={{ color: `${accent}e6` }}>
              {layer.title}
            </span>
            <p className="mt-6 text-[0.9325rem] leading-[1.74] text-[color:rgb(255_255_255_/0.66)]">{layer.body}</p>
          </motion.div>
          {idx < layers.length - 1 ? (
            <div className="hidden items-center self-center pb-14 text-xl text-[color:rgb(255_255_255_/0.2)] md:flex">→</div>
          ) : null}
        </div>
      ))}
    </div>
  );
}

function CaseDrawer({
  study,
  onClose,
}: {
  study: UnifiedCaseStudy;
  onClose: () => void;
}) {
  const { locale } = useCaseLocale();
  const L = localizeCaseStudy(study, locale);
  const accent = study.accentColor;

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const esc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", esc);
    return () => {
      document.body.style.overflow = prev;
      window.removeEventListener("keydown", esc);
    };
  }, [onClose]);

  const item = {
    hidden: { opacity: 0, y: 22 },
    show: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.74, ease: SOFT },
    },
  };

  return (
    <motion.div className="fixed inset-0 z-[92] px-5 py-8 md:p-11" initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }}>
      <button type="button" aria-label={pick(UI_LABEL.closeCase, locale)} className="absolute inset-0 bg-black/72 backdrop-blur-[2px]" onClick={onClose} />
      <motion.article
        role="dialog"
        aria-modal
        layout="position"
        className="relative z-[93] mx-auto flex max-h-[min(940px,_92vh)] w-full max-w-[1160px] flex-col gap-14 overflow-y-auto rounded-[2.02rem] border border-white/[0.09] px-9 py-10 shadow-[0_70px_150px_rgba(0,0,0,0.78)] md:gap-14 md:p-14"
        initial={{ opacity: 0.85, scale: 0.98, y: 24 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0.88, scale: 0.98, y: 18 }}
        transition={{ duration: 0.74, ease: SOFT }}
        style={{
          background: `linear-gradient(145deg,#0f1018f2,#090a12fa 46%, #050611fa)`,
        }}
      >
        <motion.div animate={{ opacity: [0.4, 0.7, 0.5] }} transition={{ repeat: Infinity, duration: 8 }}
          className="pointer-events-none absolute inset-[-1px] rounded-[inherit]" style={{
            boxShadow: `inset 0 0 80px ${accent}43`,
          }} />
        <header className="relative z-[94] flex flex-wrap items-start justify-between gap-6 gap-y-10">
          <div>
            <p className="mono text-[0.66rem] uppercase tracking-[0.34em]" style={{ color: `${accent}e8` }}>
              {L.subtitle}
            </p>
            <h2 className="mt-6 text-[clamp(2rem,5vw,2.94rem)] font-semibold leading-tight text-[var(--color-polar-white)]">{L.title}</h2>
          </div>
          <motion.button whileHover={{ scale: 1.04 }} whileTap={{ scale: 0.96 }} type="button" onClick={onClose} className="rounded-full border border-white/[0.12] px-6 py-[0.6rem] text-[0.7rem] font-semibold uppercase tracking-[0.24em]" style={{
            boxShadow: `0 0 42px ${accent}55`,
          }}>
            {pick(UI_LABEL.closeCase, locale)}
          </motion.button>
        </header>
        <div className="relative z-[94] grid flex-1 gap-14 lg:grid-cols-[minmax(0,1fr)_minmax(0,_0.9fr)]">
          <motion.div variants={{ hidden: {}, show: { transition: { staggerChildren: 0.12 } } }} initial="hidden" animate="show" className="space-y-0">
            <motion.div variants={item}>
              <CaseStudyMediaStage study={study} locale={locale} mode="drawer" motionBoost />
            </motion.div>
          </motion.div>
          <div className="space-y-14">
            <motion.section variants={item} initial="hidden" animate="show" className="">
              <SectionBanner sid="positioning" />
              <p className="text-[1.001rem] leading-[1.92] text-[color:rgb(255_255_255_/0.58)]">{L.positioning}</p>
            </motion.section>
            <motion.section variants={item}>
              <SectionBanner sid="description" />
              <p className="text-[1rem] leading-[1.88] text-[color:rgb(255_255_255_/0.54)]">{L.description}</p>
            </motion.section>
            <motion.section variants={item}>
              <SectionBanner sid="capabilities" />
              <div className="mt-8 flex flex-wrap gap-3">
                {L.capabilities.map((line) => (
                  <motion.span layout key={line.slice(0, 40)}
                    className="rounded-full border border-white/[0.08] bg-white/[0.03] px-4 py-[0.48rem] text-[0.76rem] font-medium uppercase leading-snug tracking-[0.09em]"
                    style={{ boxShadow: `inset 0 0 0 1px color-mix(in_oklab,${accent}6c,transparent)` }}
                  >
                    {line}
                  </motion.span>
                ))}
              </div>
            </motion.section>
            <motion.section variants={item}>
              <SectionBanner sid="architecture" />
              <div className="mt-10">
                <AgentRibbon accent={accent} layers={L.agents} />
              </div>
            </motion.section>
            <motion.section variants={item}>
              <SectionBanner sid="outcomes" />
              <ul className="mt-10 space-y-5 text-[0.9575rem] leading-[1.85] text-[color:rgb(255_255_255_/0.58)]">
                {L.outcomes.map((txt) => (
                  <motion.li key={txt.slice(0, 32)} variants={item} className="flex gap-5">
                    <span className="mt-3 inline-block size-2 flex-shrink-0 rounded-full bg-[linear-gradient(to_bottom,var(--accent),transparent)] bg-[linear-gradient]" style={{
                      backgroundImage: `linear-gradient(180deg,${accent},transparent)`,
                    }}
                    />
                    <span>{txt}</span>
                  </motion.li>
                ))}
              </ul>
            </motion.section>
            <motion.section variants={item}>
              <SectionBanner sid="metrics" />
              <div className="mt-10 grid grid-cols-[repeat(auto-fill,minmax(196px,_1fr))] gap-4">
                {L.metrics.map((m, i) => (
                  <motion.div key={m.value + m.label}
                    initial={{ opacity: 0, y: 18 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true, amount: 0.4 }}
                    transition={{ delay: 0.04 * i }}
                    whileHover={{ y: -2 }}
                    className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[rgba(10,11,26,0.88)] px-5 py-[0.94rem]"
                    style={{
                      boxShadow: `inset 0 0 48px ${accent}39`,
                    }}
                  >
                    <span className="text-[1.2rem] font-semibold">{m.value}</span>
                    <p className="mt-4 text-[0.85rem] text-[color:rgb(255_255_255_/0.7)]">{m.label}</p>
                    {m.detail ? (
                      <p className="mt-3 text-[0.746rem] leading-[1.6] text-[color:rgb(255_255_255_/0.44)]">{m.detail}</p>
                    ) : null}
                  </motion.div>
                ))}
              </div>
            </motion.section>
          </div>
        </div>
      </motion.article>
    </motion.div>
  );
}

function CaseShelfCard({
  study,
  onOpen,
}: {
  study: UnifiedCaseStudy;
  onOpen: (id: CaseStudyId) => void;
}) {
  const { locale } = useCaseLocale();
  const L = localizeCaseStudy(study, locale);
  const accent = study.accentColor;
  const [hover, setHover] = useState(false);

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 36 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, amount: 0.15 }}
      transition={{ duration: 0.9, ease: SOFT }}
      onHoverStart={() => setHover(true)}
      onHoverEnd={() => setHover(false)}
      className="relative mx-auto max-w-[1100px] overflow-hidden rounded-[1.94rem]"
      style={{
        boxShadow: hover ? `0 58px 120px rgba(0,0,0,0.68), inset 0 0 140px ${accent}62` : "0 40px 100px rgba(0,0,0,0.58)",
      }}
    >
      <motion.div
        animate={{
          scale: hover ? 1 : 1,
          translateY: hover ? -11 : 0,
        }}
        transition={{ duration: 0.6, ease: SOFT }}
      >
        <div className="border border-white/[0.065] bg-gradient-to-br from-[#11121c]/[0.95] via-[#0b0d17]/98 to-[#05060d]" style={{
          outline: hover ? `1px solid ${accent}55` : "1px solid transparent",
          outlineOffset: -1,
        }}>
          <CaseStudyMediaStage study={study} locale={locale} mode="card" motionBoost={hover} />
          <div className="space-y-[1.82rem] px-8 pb-10 pt-[1.7rem] md:px-[2.2rem]">
            <div>
              <p className="mono text-[0.66rem] uppercase tracking-[0.32em]" style={{ color: `${accent}ea` }}>
                {L.subtitle}
              </p>
              <h3 className="mt-8 text-[clamp(2rem,5vw,_2.7rem)] font-semibold leading-tight">{L.title}</h3>
              <p className="mt-8 max-w-3xl text-[0.9575rem] leading-[1.85] text-[color:rgb(255_255_255_/0.58)]">{L.cardDescription}</p>
            </div>
            <MetricStrip trio={L.previewMetrics} accent={accent} />
            <div>
              <motion.button
                whileHover={{ scale: 1.03 }}
                whileTap={{ scale: 0.97 }}
                type="button"
                onClick={() => onOpen(study.id)}
                className="rounded-full border border-white/15 px-[2rem] py-[0.9rem] text-[0.7825rem] font-semibold uppercase tracking-[0.2em]"
                style={{
                  background: `linear-gradient(138deg,color-mix(in_oklab,${accent}93,transparent),rgba(4,11,43,0.78))`,
                }}
              >
                {pick(UI_LABEL.openCase, locale)}
              </motion.button>
            </div>
          </div>
        </div>
      </motion.div>
    </motion.article>
  );
}

function ShowcaseCanvas() {
  const { locale, setLocale } = useCaseLocale();
  const [hoverId, setHoverId] = useState<CaseStudyId | null>(null);
  const [openId, setOpenId] = useState<CaseStudyId | null>(null);

  const openStudy = UNIFIED_CASE_STUDIES.find((c) => c.id === openId) ?? null;
  const haloId = hoverId ?? "ambient";

  return (
    <motion.section layout className="relative isolate mx-auto w-full overflow-hidden pb-26 pt-14 md:max-w-[min(1240px,_98vw)] md:pb-44 md:pt-22">
      <motion.div animate={{ rotate: haloId !== "ambient" ? 1.35 : -0.95 }} transition={{ duration: 2.9, ease: SOFT }} aria-hidden className="pointer-events-none absolute -top-[62%] right-[-40%] h-[146%] w-[146%]"
        style={{
          background: `radial-gradient(ellipse at 64% 32%,color-mix(in_oklab,${ambientAccent(haloId)}5c,transparent),transparent 64%)`,
        }}
      />

      <div className="relative z-[44] px-8 md:px-10">
        <div className="mb-36 flex flex-col gap-28 md:flex-row md:items-end md:justify-between">
          <div className="max-w-5xl space-y-[1.94rem]">
            <span className="mono text-[0.66rem] uppercase tracking-[0.36em] text-[color:rgb(255_255_255_/0.45)]">{pick(UI_LABEL.eyebrow, locale)}</span>
            <h2 className="text-[clamp(2.2rem,_5.9vw,_3.94rem)] font-semibold leading-[1.1]">{pick(UI_LABEL.headline, locale)}</h2>
            <p className="max-w-4xl text-[0.9575rem] leading-[1.9] text-[color:rgb(255_255_255_/0.55)]">{pick(UI_LABEL.sub, locale)}</p>
          </div>
          <div className="flex rounded-full border border-white/[0.12] bg-white/[0.04] p-[3px] backdrop-blur-md">
            {( ["ru","en"] as const).map((lng) => (
              <button key={lng} type="button" onClick={() => setLocale(lng)} className={`relative rounded-full px-6 py-[0.6rem] text-[0.7rem] font-semibold uppercase tracking-[0.22em]
                ${lng === locale ? "text-[#1a1b26]" : "text-[color:rgb(255_255_255_/0.54)]"}`}
              >
                {lng === locale ? (
                  <motion.span layoutId="case-lang-chip" transition={{ type: "spring", stiffness: 412, damping: 36 }} className="absolute inset-0 -z-10 rounded-full bg-gradient-to-br from-[#fcf7ee] via-[#e7daca] to-[#c2996c]" />
                ) : null}
                {lng.toUpperCase()}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-[6.44rem]">
          {UNIFIED_CASE_STUDIES.map((c) => (
            <div key={c.id} onMouseEnter={() => setHoverId(c.id)} onMouseLeave={() => setHoverId(null)}>
              <CaseShelfCard study={c} onOpen={setOpenId} />
            </div>
          ))}
        </div>
      </div>

      <AnimatePresence>{openStudy ? <CaseDrawer study={openStudy} onClose={() => setOpenId(null)} /> : null}</AnimatePresence>
    </motion.section>
  );
}

export function CasesShowcase() {
  return (
    <CaseLocaleProvider>
      <ShowcaseCanvas />
    </CaseLocaleProvider>
  );
}
