import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { extname, join, normalize, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { getConfig } from "./config.js";

const __dirname = fileURLToPath(new URL(".", import.meta.url));
const rootDir = resolve(__dirname, "..");
const webDir = resolve(rootDir, "web");
const config = getConfig(rootDir);

const mimeTypes = {
  ".css": "text/css; charset=utf-8",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml"
};

function json(res, statusCode, payload) {
  const body = JSON.stringify(payload);
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Cache-Control": "no-store"
  });
  res.end(body);
}

async function fetchGradingApiHealth() {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 1200);

  try {
    const response = await fetch(`${config.gradingApiBaseUrl}/health`, {
      cache: "no-store",
      signal: controller.signal
    });
    const payload = await response.json().catch(() => ({}));
    return {
      ok: response.ok && payload.status === "ok",
      statusCode: response.status,
      hasOpenAiKey: Boolean(payload.has_openai_key)
    };
  } catch (error) {
    return {
      ok: false,
      error: error.name === "AbortError" ? "timeout" : "unavailable"
    };
  } finally {
    clearTimeout(timeout);
  }
}

function readJsonBody(req, maxBytes) {
  return new Promise((resolveBody, rejectBody) => {
    const chunks = [];
    let size = 0;

    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > maxBytes) {
        rejectBody(Object.assign(new Error("Request body is too large"), { statusCode: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });

    req.on("end", () => {
      try {
        const raw = Buffer.concat(chunks).toString("utf8");
        resolveBody(JSON.parse(raw || "{}"));
      } catch {
        rejectBody(Object.assign(new Error("Request body must be valid JSON"), { statusCode: 400 }));
      }
    });

    req.on("error", rejectBody);
  });
}

function isSafePath(baseDir, candidatePath) {
  const relative = normalize(candidatePath).slice(normalize(baseDir).length);
  return Boolean(relative) && !relative.startsWith("..") && !resolve(candidatePath).includes("\0");
}

async function serveStatic(req, res) {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const pathname = decodeURIComponent(url.pathname);
  const routePath = pathname === "/" ? "/index.html" : pathname;
  const filePath = join(webDir, routePath);

  if (!isSafePath(webDir, filePath)) {
    json(res, 403, { error: "Forbidden" });
    return;
  }

  try {
    const content = await readFile(filePath);
    const contentType = mimeTypes[extname(filePath)] || "application/octet-stream";
    res.writeHead(200, {
      "Content-Type": contentType,
      "Cache-Control": "no-store"
    });
    res.end(content);
  } catch (error) {
    if (error.code === "ENOENT") {
      json(res, 404, { error: "Not found" });
      return;
    }

    console.error(error);
    json(res, 500, { error: "Internal server error" });
  }
}

async function proxyJsonToGradingApi(req, res, path) {
  let payload;

  try {
    payload = await readJsonBody(req, config.maxProxyBodyBytes);
  } catch (error) {
    json(res, error.statusCode || 400, {
      error: error.statusCode === 413 ? "payload_too_large" : "bad_request",
      message: error.message
    });
    return;
  }

  const headers = {
    "Content-Type": "application/json"
  };

  if (config.gradingApiToken) {
    headers["X-Grading-Api-Token"] = config.gradingApiToken;
  }

  let gradingResponse;
  let gradingBody;

  try {
    gradingResponse = await fetch(`${config.gradingApiBaseUrl}${path}`, {
      method: "POST",
      headers,
      body: JSON.stringify(payload)
    });
    gradingBody = await gradingResponse.json();
  } catch {
    json(res, 502, {
      error: "grading_api_unavailable",
      message: "评分 API 暂不可用，请确认 Python 服务已启动。"
    });
    return;
  }

  json(res, gradingResponse.status, gradingBody);
}

async function proxyGetToGradingApi(res, path) {
  const headers = {};

  if (config.gradingApiToken) {
    headers["X-Grading-Api-Token"] = config.gradingApiToken;
  }

  let gradingResponse;
  let gradingBody;

  try {
    gradingResponse = await fetch(`${config.gradingApiBaseUrl}${path}`, {
      method: "GET",
      headers,
      cache: "no-store"
    });
    gradingBody = await gradingResponse.json();
  } catch {
    json(res, 502, {
      error: "grading_api_unavailable",
      message: "评分 API 暂不可用，请确认 Python 服务已启动。"
    });
    return;
  }

  json(res, gradingResponse.status, gradingBody);
}

const server = createServer(async (req, res) => {
  if (req.method === "GET" && req.url?.startsWith("/api/health")) {
    const gradingApi = await fetchGradingApiHealth();
    json(res, 200, {
      ok: true,
      service: "exam-grading-assistant",
      hasOpenAiKey: config.hasOpenAiKey,
      gradingApiBaseUrl: config.gradingApiBaseUrl,
      gradingApi
    });
    return;
  }

  if (req.method === "GET" && req.url?.startsWith("/api/mouse-position")) {
    await proxyGetToGradingApi(res, "/api/mouse-position");
    return;
  }

  if (req.method === "POST" && req.url?.startsWith("/api/grade-answer")) {
    await proxyJsonToGradingApi(req, res, "/api/grade");
    return;
  }

  if (req.method === "POST" && req.url?.startsWith("/api/parse-reference")) {
    await proxyJsonToGradingApi(req, res, "/api/parse-reference");
    return;
  }

  if (req.method === "POST" && req.url?.startsWith("/api/click-sequence")) {
    await proxyJsonToGradingApi(req, res, "/api/click-sequence");
    return;
  }

  if (req.method === "POST" && req.url?.startsWith("/api/click")) {
    await proxyJsonToGradingApi(req, res, "/api/click");
    return;
  }

  if (req.method === "GET") {
    await serveStatic(req, res);
    return;
  }

  json(res, 405, { error: "Method not allowed" });
});

server.listen(config.port, "127.0.0.1", () => {
  console.log(`Exam grading assistant running at http://localhost:${config.port}`);
});
