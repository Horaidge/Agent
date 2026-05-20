import { VoiceScreen } from "@/components/voice-screen";

export default function VoicePage() {
  const publicKey = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY ?? "";
  const assistantId = process.env.NEXT_PUBLIC_VAPI_ASSISTANT_ID ?? "";

  return <VoiceScreen publicKey={publicKey} assistantId={assistantId} />;
}
