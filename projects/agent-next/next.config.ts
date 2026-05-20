import type { NextConfig } from "next";
import fs from "fs";
import path from "path";
import { fileURLToPath } from "url";

const configDir = path.dirname(fileURLToPath(import.meta.url));

/**
 * Next 16 + Turbopack: NEXT_PUBLIC_* из .env.local иногда не попадают в process.env
 * до рендера серверных компонентов. Подмешиваем файлы до остальной инициализации
 * (тот же паттерн, что в projects/agent/app/next.config.mjs).
 */
function mergeEnvFromFile(filePath: string) {
  if (!fs.existsSync(filePath)) return;
  const raw = fs.readFileSync(filePath, "utf8");
  for (const line of raw.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq === -1) continue;
    const key = trimmed.slice(0, eq).trim();
    let val = trimmed.slice(eq + 1).trim();
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    if (!key) continue;
    if (process.env[key] === undefined || process.env[key] === "") {
      process.env[key] = val;
    }
  }
}

mergeEnvFromFile(path.join(configDir, ".env.local"));
mergeEnvFromFile(path.join(configDir, ".env"));

const nextConfig: NextConfig = {};

export default nextConfig;
