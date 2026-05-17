type RawDebugRecord = {
  kind: "raw-event";
  sessionId: string;
  callId: string | null;
  timestamp: string;
  eventType: string;
  payload: unknown;
};

const queue: RawDebugRecord[] = [];
let timer: ReturnType<typeof setTimeout> | null = null;
let flushing = false;

async function flushQueue() {
  if (flushing || queue.length === 0 || typeof window === "undefined") return;
  flushing = true;
  const records = queue.splice(0, queue.length);
  try {
    await fetch("/api/debug-ingest", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        kind: "raw-events-batch",
        records,
      }),
      keepalive: true,
    });
  } catch {
    // Ignore network errors in client logger.
  } finally {
    flushing = false;
  }
}

export function enqueueRawDebugRecord(record: RawDebugRecord) {
  if (typeof window === "undefined") return;
  queue.push(record);
  if (queue.length >= 20) {
    void flushQueue();
    return;
  }
  if (!timer) {
    timer = setTimeout(() => {
      timer = null;
      void flushQueue();
    }, 1200);
  }
}
