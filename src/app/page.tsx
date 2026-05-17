import { LandingPage } from "@/components/landing/landing-page";

export default function Home() {
  const publicKey = process.env.NEXT_PUBLIC_VAPI_PUBLIC_KEY ?? "";
  const assistantId = process.env.NEXT_PUBLIC_VAPI_ASSISTANT_ID ?? "";

  return <LandingPage publicKey={publicKey} assistantId={assistantId} />;
}
