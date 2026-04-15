"use client"

import { useState, useEffect } from "react"
import { MessageCircle, X, Mic } from "lucide-react"
import { Button } from "@/components/ui/button"
import { OPEN_CHAT_EVENT } from "@/lib/chat-events"
import { cn } from "@/lib/utils"

type Message = { role: "user" | "assistant"; text: string }

export function ChatWidget() {
  const [isOpen, setIsOpen] = useState(false)
  const [messages, setMessages] = useState<Message[]>([])

  useEffect(() => {
    const handler = () => setIsOpen(true)
    window.addEventListener(OPEN_CHAT_EVENT, handler)
    return () => window.removeEventListener(OPEN_CHAT_EVENT, handler)
  }, [])

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
      {isOpen && (
        <div
          className={cn(
            "w-[360px] max-w-[calc(100vw-48px)] h-[480px] max-h-[70vh]",
            "bg-background border border-border rounded-2xl shadow-xl",
            "flex flex-col overflow-hidden"
          )}
        >
          <div className="flex items-center justify-between p-4 border-b border-border">
            <span className="font-semibold text-foreground">Чат с агентом</span>
            <Button variant="ghost" size="icon" onClick={() => setIsOpen(false)} aria-label="Закрыть">
              <X className="w-4 h-4" />
            </Button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-3">
            {messages.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-8">
                Напишите сообщение или нажмите на микрофон, чтобы начать голосовой разговор.
              </p>
            )}
            {messages.map((m, i) => (
              <div
                key={i}
                className={cn(
                  "text-sm rounded-lg px-3 py-2 max-w-[85%]",
                  m.role === "user"
                    ? "bg-primary text-primary-foreground ml-auto"
                    : "bg-muted text-foreground"
                )}
              >
                {m.text}
              </div>
            ))}
          </div>

          <div className="p-3 border-t border-border flex gap-2">
            <input
              type="text"
              placeholder="Сообщение..."
              className="flex-1 rounded-lg border border-input bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault()
                  const text = e.currentTarget.value.trim()
                  if (text) {
                    setMessages((prev) => [...prev, { role: "user", text }])
                    e.currentTarget.value = ""
                  }
                }
              }}
            />
            <Button size="icon" variant="outline" aria-label="Голос" title="Голосовой ввод">
              <Mic className="w-4 h-4" />
            </Button>
          </div>
        </div>
      )}

      <Button
        size="lg"
        className="rounded-full w-14 h-14 shadow-lg"
        onClick={() => setIsOpen((o) => !o)}
        aria-label={isOpen ? "Закрыть чат" : "Открыть чат"}
      >
        <MessageCircle className="w-6 h-6" />
      </Button>
    </div>
  )
}
