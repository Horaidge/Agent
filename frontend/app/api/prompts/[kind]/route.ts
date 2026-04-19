import { NextRequest, NextResponse } from "next/server"

function backendBase(): string {
  return (process.env.CONTENT_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "")
}

function editorSecret(): string | null {
  const s = process.env.PROMPTS_EDITOR_SECRET
  if (!s?.trim()) return null
  return s.trim()
}

const ALLOWED = new Set(["system", "global-policy"])

export async function GET(
  _request: NextRequest,
  context: { params: Promise<{ kind: string }> }
) {
  const { kind } = await context.params
  if (!ALLOWED.has(kind)) {
    return NextResponse.json({ detail: "unknown kind" }, { status: 404 })
  }
  const sec = editorSecret()
  if (!sec) {
    return NextResponse.json(
      {
        detail:
          "Задайте PROMPTS_EDITOR_SECRET в frontend (.env.local) — тот же ключ, что в backend (projects/content/.env).",
      },
      { status: 500 }
    )
  }
  const r = await fetch(`${backendBase()}/api/prompts/${kind}`, {
    headers: { Authorization: `Bearer ${sec}` },
    cache: "no-store",
  })
  const text = await r.text()
  try {
    const data = JSON.parse(text) as unknown
    return NextResponse.json(data, { status: r.status })
  } catch {
    return new NextResponse(text, {
      status: r.status,
      headers: { "Content-Type": r.headers.get("Content-Type") || "text/plain" },
    })
  }
}

export async function PUT(
  request: NextRequest,
  context: { params: Promise<{ kind: string }> }
) {
  const { kind } = await context.params
  if (!ALLOWED.has(kind)) {
    return NextResponse.json({ detail: "unknown kind" }, { status: 404 })
  }
  const sec = editorSecret()
  if (!sec) {
    return NextResponse.json(
      {
        detail:
          "Задайте PROMPTS_EDITOR_SECRET в frontend (.env.local) — тот же ключ, что в backend.",
      },
      { status: 500 }
    )
  }
  let body: unknown
  try {
    body = await request.json()
  } catch {
    return NextResponse.json({ detail: "Invalid JSON body" }, { status: 400 })
  }
  const r = await fetch(`${backendBase()}/api/prompts/${kind}`, {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${sec}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  })
  const text = await r.text()
  try {
    const data = JSON.parse(text) as unknown
    return NextResponse.json(data, { status: r.status })
  } catch {
    return new NextResponse(text, {
      status: r.status,
      headers: { "Content-Type": r.headers.get("Content-Type") || "text/plain" },
    })
  }
}
