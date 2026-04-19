import type { Metadata } from "next"

export const metadata: Metadata = {
  title: "Редактор промптов",
  description: "Редактирование system_prompt.md и global_model_policy.md для backend",
}

export default function PromptEditorLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return children
}
