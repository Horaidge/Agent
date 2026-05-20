/**
 * Optional preflight — Vapi also requests mic; this can surface errors early.
 */
export async function warmUpMicrophonePermission(): Promise<{ ok: true } | { ok: false; reason: string }> {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    return { ok: false, reason: "API микрофона недоступен в этой среде" };
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    stream.getTracks().forEach((t) => t.stop());
    return { ok: true };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    if (/not allowed|permission/i.test(msg)) {
      return { ok: false, reason: "Нужен доступ к микрофону" };
    }
    return { ok: false, reason: "Не удалось открыть микрофон" };
  }
}
