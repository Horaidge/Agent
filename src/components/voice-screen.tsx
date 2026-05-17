"use client";

import dynamic from "next/dynamic";
import { useVoiceSession } from "@/orchestration/use-voice-session";

const CinematicHero = dynamic(
  () => import("@/components/cinematic-hero").then((m) => m.CinematicHero),
  { ssr: false },
);

type VoiceScreenProps = {
  publicKey: string;
  assistantId: string;
};

const labelForStatus: Record<string, string> = {
  idle: "Готов к разговору",
  connecting: "Подключение…",
  connected: "Слушаем",
  speaking: "Идёт речь",
  error: "Ошибка",
};

export function VoiceScreen({ publicKey, assistantId }: VoiceScreenProps) {
  const { status, errorMessage, activeSpeaker, toggle } = useVoiceSession(publicKey, assistantId);

  const buttonLabel =
    status === "idle" || status === "error"
      ? "Поговорить с агентом"
      : status === "connecting"
        ? "Подключение…"
        : "Завершить разговор";

  const disabled = status === "connecting";

  return (
    <div className="relative min-h-dvh bg-zinc-950 text-zinc-100">
      <div className="pointer-events-none fixed inset-0 z-0">
        <CinematicHero />
      </div>
      <div className="relative z-10 flex min-h-dvh flex-col items-center justify-center px-6">
        <div className="flex max-w-md flex-col items-center gap-8 text-center">
        <p className="text-sm tracking-wide text-zinc-500">{labelForStatus[status] ?? status}</p>
        {status === "speaking" && activeSpeaker && (
          <p className="text-xs text-zinc-600">
            {activeSpeaker === "user" ? "Вы говорите" : "Ассистент говорит"}
          </p>
        )}
        <button
          type="button"
          disabled={disabled}
          onClick={toggle}
          className="min-h-14 min-w-[min(100%,18rem)] rounded-xl bg-zinc-100 px-8 py-4 text-base font-medium text-zinc-950 shadow-sm transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {buttonLabel}
        </button>
        {status === "error" && errorMessage && (
          <p className="text-sm text-red-400" role="alert">
            {errorMessage}
          </p>
        )}
        {!publicKey.trim() || !assistantId.trim() ? (
          <p className="text-xs text-amber-400/90">
            Скопируйте <code className="rounded bg-zinc-900 px-1">.env.example</code> в{" "}
            <code className="rounded bg-zinc-900 px-1">.env.local</code> и укажите ключи VAPI (не
            продовые секреты в git).
          </p>
        ) : null}
        </div>
      </div>
    </div>
  );
}
