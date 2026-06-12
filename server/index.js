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

const server = createServer(async (req, res) => {
  if (req.method === "GET" && req.url?.startsWith("/api/health")) {
    json(res, 200, {
      ok: true,
      service: "exam-grading-assistant",
      hasOpenAiKey: config.hasOpenAiKey
    });
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
