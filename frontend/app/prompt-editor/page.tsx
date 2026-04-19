"use client"

import { useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { ArrowLeft, Save } from "lucide-react"
import { toast, Toaster } from "sonner"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { cn } from "@/lib/utils"

type PromptKind = "system" | "global-policy"

function errMessage(data: unknown, fallback: string): string {
  if (data && typeof data === "object" && "detail" in data) {
    const d = (data as { detail: unknown }).detail
    if (typeof d === "string") return d
    if (Array.isArray(d)) return JSON.stringify(d)
  }
  return fallback
}

export default function PromptEditorPage() {
  const [system, setSystem] = useState("")
  const [globalPolicy, setGlobalPolicy] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState<PromptKind | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)

  const fetchKind = useCallback(async (kind: PromptKind): Promise<string> => {
    const r = await fetch(`/api/prompts/${kind}`, { cache: "no-store" })
    const data = (await r.json()) as { content?: string; detail?: unknown }
    if (!r.ok) {
      throw new Error(errMessage(data, `HTTP ${r.status}`))
    }
    if (typeof data.content !== "string") {
      throw new Error("Некорректный ответ API (нет content)")
    }
    return data.content
  }, [])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setLoadError(null)
      try {
        const [s, g] = await Promise.all([fetchKind("system"), fetchKind("global-policy")])
        if (!cancelled) {
          setSystem(s)
          setGlobalPolicy(g)
        }
      } catch (e) {
        if (!cancelled) {
          setLoadError(e instanceof Error ? e.message : String(e))
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [fetchKind])

  const save = async (kind: PromptKind) => {
    const content = kind === "system" ? system : globalPolicy
    setSaving(kind)
    try {
      const r = await fetch(`/api/prompts/${kind}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      })
      const data = await r.json()
      if (!r.ok) {
        throw new Error(errMessage(data, `HTTP ${r.status}`))
      }
      toast.success(
        kind === "system"
          ? "Сохранено: prompts/system_prompt.md"
          : "Сохранено: prompts/global_model_policy.md"
      )
    } catch (e) {
      toast.error(e instanceof Error ? e.message : String(e))
    } finally {
      setSaving(null)
    }
  }

  return (
    <div className="min-h-screen bg-background text-foreground">
      <Toaster richColors position="top-center" />
      <div className="border-b border-border bg-card/50">
        <div className="max-w-4xl mx-auto px-4 py-4 flex items-center gap-4">
          <Button variant="ghost" size="sm" asChild>
            <Link href="/" className="gap-2">
              <ArrowLeft className="h-4 w-4" />
              На главную
            </Link>
          </Button>
          <h1 className="text-lg font-semibold">Редактор системных промптов</h1>
        </div>
      </div>

      <main className="max-w-4xl mx-auto px-4 py-8">
        <p className="text-sm text-muted-foreground mb-6">
          Тексты читаются и пишутся в каталоге backend{" "}
          <code className="text-xs bg-muted px-1 py-0.5 rounded">projects/content/prompts/</code>.
          После сохранения следующий запрос к модели подхватит изменения без перезапуска сервера.
        </p>

        {loadError && (
          <div
            className={cn(
              "mb-6 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm",
              "text-destructive"
            )}
          >
            <p className="font-medium">Не удалось загрузить промпты</p>
            <p className="mt-1 opacity-90">{loadError}</p>
            <p className="mt-2 text-muted-foreground text-xs">
              Убедитесь, что backend запущен, в{" "}
              <code className="bg-muted px-1 rounded">projects/content/.env</code> задан{" "}
              <code className="bg-muted px-1 rounded">PROMPTS_EDITOR_SECRET</code>, и в{" "}
              <code className="bg-muted px-1 rounded">frontend/.env.local</code> — тот же секрет и при
              необходимости <code className="bg-muted px-1 rounded">CONTENT_API_BASE_URL</code>.
            </p>
          </div>
        )}

        <Tabs defaultValue="system" className="w-full">
          <TabsList className="grid w-full max-w-md grid-cols-2">
            <TabsTrigger value="system">system_prompt.md</TabsTrigger>
            <TabsTrigger value="global">global_model_policy.md</TabsTrigger>
          </TabsList>
          <TabsContent value="system" className="mt-4 space-y-4">
            <Textarea
              className="min-h-[420px] font-mono text-sm"
              value={system}
              onChange={(e) => setSystem(e.target.value)}
              disabled={loading || !!loadError}
              placeholder="Загрузка…"
              spellCheck={false}
            />
            <Button
              onClick={() => void save("system")}
              disabled={loading || !!loadError || saving !== null}
            >
              <Save className="h-4 w-4 mr-2" />
              {saving === "system" ? "Сохранение…" : "Сохранить системный промпт"}
            </Button>
          </TabsContent>
          <TabsContent value="global" className="mt-4 space-y-4">
            <p className="text-xs text-muted-foreground">
              Дополнительный system-слой ко всем вызовам модели (можно оставить пустым).
            </p>
            <Textarea
              className="min-h-[320px] font-mono text-sm"
              value={globalPolicy}
              onChange={(e) => setGlobalPolicy(e.target.value)}
              disabled={loading || !!loadError}
              placeholder="Загрузка…"
              spellCheck={false}
            />
            <Button
              onClick={() => void save("global-policy")}
              disabled={loading || !!loadError || saving !== null}
            >
              <Save className="h-4 w-4 mr-2" />
              {saving === "global-policy" ? "Сохранение…" : "Сохранить политику"}
            </Button>
          </TabsContent>
        </Tabs>
      </main>
    </div>
  )
}
