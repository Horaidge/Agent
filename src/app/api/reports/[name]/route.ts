import { promises as fs } from "fs";
import path from "path";
import { NextResponse } from "next/server";

const allowedFiles = new Map<string, string>([
  ["dependency-cruiser-report.html", "text/html; charset=utf-8"],
  ["dependency-cruiser-graph.txt", "text/plain; charset=utf-8"],
  ["dependency-cruiser-graph.mmd", "text/plain; charset=utf-8"],
  ["dependency-cruiser-report.json", "application/json; charset=utf-8"],
  ["dependency-cruiser-graph.dot", "text/plain; charset=utf-8"],
]);

export async function GET(
  _request: Request,
  context: { params: Promise<{ name: string }> },
) {
  const { name } = await context.params;
  const contentType = allowedFiles.get(name);
  if (!contentType) {
    return NextResponse.json({ error: "Report is not allowed." }, { status: 404 });
  }

  const absolutePath = path.join(process.cwd(), "reports", name);
  try {
    const content = await fs.readFile(absolutePath);
    return new NextResponse(content, {
      status: 200,
      headers: {
        "content-type": contentType,
        "cache-control": "no-store",
      },
    });
  } catch {
    return NextResponse.json(
      { error: `Report '${name}' not found. Run pnpm depcruise:json/depcruise:dot first.` },
      { status: 404 },
    );
  }
}
