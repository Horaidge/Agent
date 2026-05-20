/** Minimal type guards for Vapi `message` events (foundation only). */

export type VapiSpeechUpdateMessage = {
  type: "speech-update";
  role: "user" | "assistant";
  status: "started" | "stopped";
};

export type VapiTranscriptMessage =
  | {
      type: "transcript";
      role: "user" | "assistant" | "system";
      transcript: string;
      transcriptType?: "partial" | "final";
    }
  | {
      type: "conversation-update";
      conversation?: {
        messages?: Array<{
          role?: "user" | "assistant" | "system";
          content?: string;
        }>;
      };
    };

export type ExtractedToolCall = {
  name: string;
  status: "queued" | "running" | "done";
  summary: string;
  rawPayload?: string;
};

export function isSpeechUpdateMessage(msg: unknown): msg is VapiSpeechUpdateMessage {
  if (!msg || typeof msg !== "object") return false;
  const m = msg as Record<string, unknown>;
  return (
    m.type === "speech-update" &&
    (m.role === "user" || m.role === "assistant") &&
    (m.status === "started" || m.status === "stopped")
  );
}

export function extractFinalTranscriptMessage(
  msg: unknown,
): { role: "user" | "assistant" | "system"; content: string } | null {
  if (!msg || typeof msg !== "object") return null;
  const m = msg as Record<string, unknown>;

  if (
    m.type === "transcript" &&
    (m.role === "user" || m.role === "assistant" || m.role === "system") &&
    typeof m.transcript === "string"
  ) {
    const transcriptType = m.transcriptType;
    if (transcriptType === "partial") return null;
    const content = m.transcript.trim();
    if (!content) return null;
    return { role: m.role, content };
  }

  if (m.type === "conversation-update") {
    const convo = m.conversation as { messages?: Array<{ role?: unknown; content?: unknown }> } | undefined;
    const latest = convo?.messages?.at(-1);
    if (!latest) return null;
    if (
      (latest.role === "user" || latest.role === "assistant" || latest.role === "system") &&
      typeof latest.content === "string" &&
      latest.content.trim()
    ) {
      return { role: latest.role, content: latest.content.trim() };
    }
  }

  return null;
}

function stringifyUnknown(payload: unknown): string {
  try {
    return JSON.stringify(payload);
  } catch {
    return String(payload);
  }
}

function parseMaybeJsonObject(payload: unknown): Record<string, unknown> | null {
  if (payload && typeof payload === "object") {
    return payload as Record<string, unknown>;
  }
  if (typeof payload === "string") {
    try {
      const parsed = JSON.parse(payload) as unknown;
      return parsed && typeof parsed === "object" ? (parsed as Record<string, unknown>) : null;
    } catch {
      return null;
    }
  }
  return null;
}

function extractToolIdentity(tool: Record<string, unknown>): {
  name: string;
  args: unknown;
  result: unknown;
} {
  const fn =
    tool.function && typeof tool.function === "object"
      ? (tool.function as Record<string, unknown>)
      : null;
  const name =
    (typeof tool.name === "string" && tool.name) ||
    (typeof tool.toolName === "string" && tool.toolName) ||
    (typeof tool.functionName === "string" && tool.functionName) ||
    (typeof fn?.name === "string" && fn.name) ||
    (typeof tool.id === "string" && tool.id) ||
    "unknown-tool";
  const args = tool.arguments ?? tool.args ?? tool.input ?? tool.parameters ?? fn?.arguments;
  const result = tool.result ?? tool.output;
  return { name, args, result };
}

export function extractToolCalls(msg: unknown): ExtractedToolCall[] {
  if (!msg || typeof msg !== "object") return [];
  const m = msg as Record<string, unknown>;
  const found: ExtractedToolCall[] = [];

  const directToolCalls =
    (Array.isArray(m.toolCalls) ? m.toolCalls : null) ??
    (Array.isArray(m.tool_calls) ? m.tool_calls : null) ??
    (Array.isArray(m["tool-calls"]) ? (m["tool-calls"] as unknown[]) : null);

  if (directToolCalls) {
    for (const item of directToolCalls) {
      if (!item || typeof item !== "object") continue;
      const tool = item as Record<string, unknown>;
      const { name, args, result } = extractToolIdentity(tool);
      const status =
        tool.status === "failed" || tool.status === "error"
          ? "done"
          : tool.status === "queued"
            ? "queued"
            : tool.status === "running"
              ? "running"
              : "done";

      found.push({
        name,
        status,
        summary: result
          ? `result: ${stringifyUnknown(result).slice(0, 160)}`
          : `args: ${stringifyUnknown(args).slice(0, 160)}`,
        rawPayload: stringifyUnknown(tool),
      });
    }
  }

  if (Array.isArray(m.toolCallList)) {
    for (const item of m.toolCallList) {
      if (!item || typeof item !== "object") continue;
      const tool = item as Record<string, unknown>;
      const { name, args, result } = extractToolIdentity(tool);
      found.push({
        name,
        status: "running",
        summary: result
          ? `result: ${stringifyUnknown(result).slice(0, 160)}`
          : `args: ${stringifyUnknown(args).slice(0, 160)}`,
        rawPayload: stringifyUnknown(tool),
      });
    }
  }

  if (m.type === "tool-call" || m.type === "function-call") {
    const name =
      (typeof m.toolName === "string" && m.toolName) ||
      (typeof m.name === "string" && m.name) ||
      (typeof m.functionName === "string" && m.functionName) ||
      "unknown-tool";
    const args = m.arguments ?? m.args ?? m.input;
    found.push({
      name,
      status: "running",
      summary: `args: ${stringifyUnknown(args).slice(0, 160)}`,
      rawPayload: stringifyUnknown(m),
    });
  }

  if (m.type === "conversation-update") {
    const convo = m.conversation as
      | { messages?: Array<{ role?: unknown; content?: unknown; toolName?: unknown; tool_calls?: unknown }> }
      | undefined;
    for (const message of convo?.messages ?? []) {
      if (!message || typeof message !== "object") continue;
      if (message.role === "tool") {
        const toolName = typeof message.toolName === "string" ? message.toolName : "tool-result";
        const content =
          typeof message.content === "string" ? message.content : stringifyUnknown(message.content);
        found.push({
          name: toolName,
          status: "done",
          summary: `result: ${content.slice(0, 160)}`,
          rawPayload: stringifyUnknown(message),
        });
      }

      const toolCalls = Array.isArray(message.tool_calls) ? message.tool_calls : [];
      for (const toolCall of toolCalls) {
        if (!toolCall || typeof toolCall !== "object") continue;
        const parsed = toolCall as Record<string, unknown>;
        const { name, args } = extractToolIdentity(parsed);
        found.push({
          name,
          status: "running",
          summary: `args: ${stringifyUnknown(args).slice(0, 160)}`,
          rawPayload: stringifyUnknown(parsed),
        });
      }
    }
  }

  const deduped = new Map<string, ExtractedToolCall>();
  for (const toolCall of found) {
    const rawObj = parseMaybeJsonObject(toolCall.rawPayload ?? null);
    const key = `${toolCall.name}|${toolCall.status}|${stringifyUnknown(rawObj ?? toolCall.summary)}`;
    if (!deduped.has(key)) deduped.set(key, toolCall);
  }
  return [...deduped.values()];
}
