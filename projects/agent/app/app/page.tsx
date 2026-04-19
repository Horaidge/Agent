import { MainVoicePage } from "@/components/main-voice-page";

/**
 * Серверный компонент: здесь process.env подхватывает .env.local надёжно,
 * затем значения передаются в клиент (в отличие от чтения env внутри хуков с Turbopack).
 */
export default function Page() {
  const publicKey = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY ?? "";
  const assistantId = process.env.NEXT_PUBLIC_VAPI_ASSISTANT_ID ?? "";

  return (
    <MainVoicePage vapiPublicKey={publicKey} vapiAssistantId={assistantId} />
  );
}
