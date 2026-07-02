import { readFileSync } from "node:fs";
import { resolve } from "node:path";

export function loadEnv(rootDir) {
  const envPath = resolve(rootDir, ".env");

  try {
    const content = readFileSync(envPath, "utf8");

    for (const line of content.split(/\r?\n/)) {
      const trimmed = line.trim();

      if (!trimmed || trimmed.startsWith("#")) {
        continue;
      }

      const separator = trimmed.indexOf("=");
      if (separator === -1) {
        continue;
      }

      const key = trimmed.slice(0, separator).trim();
      const value = trimmed.slice(separator + 1).trim();

      if (key && !globalThis.process?.env?.[key]) {
        globalThis.process.env[key] = value;
      }
    }
  } catch (error) {
    if (error.code !== "ENOENT") {
      throw error;
    }
  }
}

export function getConfig(rootDir) {
  loadEnv(rootDir);

  const openAiApiKey =
    globalThis.process.env.OPENAI_API_KEY ||
    globalThis.process.env.AI_KEY_TEST_API_KEY ||
    globalThis.process.env.DEEPSEEK_API_KEY ||
    "";
  const gradingApiBaseUrl = (
    globalThis.process.env.GRADING_API_URL ||
    `http://${globalThis.process.env.GRADING_API_HOST || "127.0.0.1"}:${globalThis.process.env.GRADING_API_PORT || "8765"}`
  ).replace(/\/+$/, "");

  return {
    port: Number.parseInt(globalThis.process.env.PORT || "5173", 10),
    hasOpenAiKey: Boolean(openAiApiKey),
    gradingApiBaseUrl,
    gradingApiToken: globalThis.process.env.GRADING_API_TOKEN || "",
    maxProxyBodyBytes: Number.parseInt(
      globalThis.process.env.GRADING_PROXY_MAX_BODY_BYTES || String(24 * 1024 * 1024),
      10
    )
  };
}
