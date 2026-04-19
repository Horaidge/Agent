/**
 * Нормализация tool calls от Vapi / OpenAI (в т.ч. вложенный `function: { name, arguments }` и `id`).
 */

export function extractToolCallId(o: Record<string, unknown>): string | undefined {
  const id = o.id ?? o.toolCallId ?? o.tool_call_id;
  return typeof id === "string" && id.length > 0 ? id : undefined;
}

export function normalizeIncomingToolCall(tc: unknown): {
  toolCallId?: string;
  rawName?: string;
  rawArgs: Record<string, unknown>;
} {
  if (!tc || typeof tc !== "object") return { rawArgs: {} };
  const o = tc as Record<string, unknown>;
  const toolCallId = extractToolCallId(o);
  const fn = o.function as Record<string, unknown> | undefined;
  const rawName =
    (typeof o.name === "string" ? o.name : undefined) ?? (typeof fn?.name === "string" ? fn.name : undefined);
  let parsed: unknown = o.arguments ?? fn?.arguments;
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      parsed = {};
    }
  }
  const rawArgs =
    parsed && typeof parsed === "object" && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {};
  return { toolCallId, rawName, rawArgs };
}

export type LooseToolCall = {
  id?: string;
  name?: string;
  arguments: Record<string, unknown>;
};

/** Разбор сырых сообщений, где tool calls могут лежать в `toolCalls` или `tool_calls`. */
export function extractLooseToolCallsFromRaw(raw: unknown): LooseToolCall[] {
  if (!raw || typeof raw !== "object") return [];
  const obj = raw as Record<string, unknown>;

  const fromArray = (arr: unknown[]): LooseToolCall[] =>
    arr.map((item) => {
      const n = normalizeIncomingToolCall(item);
      return { id: n.toolCallId, name: n.rawName, arguments: n.rawArgs };
    });

  if (Array.isArray(obj.toolCalls)) {
    return fromArray(obj.toolCalls);
  }

  if (Array.isArray(obj.tool_calls)) {
    return fromArray(obj.tool_calls);
  }

  if (obj.type === "tool-calls" && Array.isArray(obj.toolCalls)) {
    return fromArray(obj.toolCalls);
  }

  return [];
}
