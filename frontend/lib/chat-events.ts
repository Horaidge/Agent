export const OPEN_CHAT_EVENT = "dzen-open-chat"

export function dispatchOpenChat() {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new CustomEvent(OPEN_CHAT_EVENT))
  }
}
