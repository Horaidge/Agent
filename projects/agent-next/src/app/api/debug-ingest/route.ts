import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";

export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const reportsDir = path.join(process.cwd(), "reports");
    const targetFile = path.join(reportsDir, "debug-sessions.ndjson");
    await fs.mkdir(reportsDir, { recursive: true });
    const records = Array.isArray(payload?.records)
      ? (payload.records as unknown[])
      : [payload];
    const lines = records.map((record) => JSON.stringify(record)).join("\n");
    await fs.appendFile(targetFile, `${lines}\n`, "utf8");
    return NextResponse.json({ ok: true });
  } catch (error) {
    return NextResponse.json(
      { ok: false, error: error instanceof Error ? error.message : "debug ingest failed" },
      { status: 500 },
    );
  }
}
