import { createRequire } from "node:module";
import path from "node:path";
import { createInterface } from "node:readline";
import { pathToFileURL } from "node:url";

const require = createRequire(import.meta.url);

function parseArgs(argv) {
  const result = {};
  for (let i = 0; i < argv.length; i += 2) {
    result[argv[i].replace(/^--/, "")] = argv[i + 1];
  }
  return result;
}

const args = parseArgs(process.argv.slice(2));
const pluginPath = args.plugin;
const cacheDir = args["cache-dir"];
const pluginId = args["plugin-id"];

if (!pluginPath || !cacheDir || !pluginId) {
  throw new Error("missing required bridge arguments");
}

function cachePath(rule, key) {
  const safeRule = String(rule || "default").replace(/[^a-zA-Z0-9_.-]/g, "_");
  const safeKey = String(key || "").replace(/[^a-zA-Z0-9_.-]/g, "_");
  return path.join(cacheDir, "js-local", String(pluginId), safeRule, `${safeKey}.txt`);
}

globalThis.local = {
  get(rule, key) {
    try {
      return require("node:fs").readFileSync(cachePath(rule, key), "utf-8");
    } catch {
      return "";
    }
  },
  set(rule, key, value) {
    const file = cachePath(rule, key);
    require("node:fs").mkdirSync(path.dirname(file), { recursive: true });
    require("node:fs").writeFileSync(file, String(value ?? ""), "utf-8");
  },
  delete(rule, key) {
    try {
      require("node:fs").unlinkSync(cachePath(rule, key));
    } catch {
    }
  },
};

async function http(url, options = {}) {
  const response = await fetch(url, options);
  const text = await response.text();
  return {
    ok: response.ok,
    status: response.status,
    url: response.url,
    headers: Object.fromEntries(response.headers.entries()),
    content: text,
    text,
    json: () => JSON.parse(text),
  };
}

globalThis.http = http;
globalThis.req = http;

const originalConsole = globalThis.console;
globalThis.console = {
  log: (...items) => originalConsole.error(JSON.stringify({ level: "info", message: items.map(String).join(" ") })),
  warn: (...items) => originalConsole.error(JSON.stringify({ level: "warning", message: items.map(String).join(" ") })),
  error: (...items) => originalConsole.error(JSON.stringify({ level: "error", message: items.map(String).join(" ") })),
};

const pluginModule = await import(pathToFileURL(pluginPath).href);
let spider = null;
if (typeof pluginModule.__jsEvalReturn === "function") {
  spider = await pluginModule.__jsEvalReturn();
} else if (typeof pluginModule.default === "function") {
  spider = await pluginModule.default();
} else if (pluginModule.default) {
  spider = pluginModule.default;
} else {
  spider = pluginModule;
}

if (!spider || typeof spider !== "object") {
  throw new Error("JavaScript plugin did not export a spider object");
}

function normalizeResult(value) {
  if (typeof value === "string") {
    try {
      return JSON.parse(value);
    } catch {
      return value;
    }
  }
  return value;
}

async function callMethod(method, args) {
  const map = {
    init: "init",
    home: "home",
    category: "category",
    detail: "detail",
    search: "search",
    play: "play",
    getName: "getName",
    destroy: "destroy",
  };
  if (method === "hasMethod") return typeof spider[args[0]] === "function";
  const jsName = map[method];
  const fn = jsName ? spider[jsName] : null;
  if (typeof fn !== "function") {
    if (method === "init" || method === "destroy") return null;
    throw new Error(`${method} is not defined`);
  }
  return normalizeResult(await fn.apply(spider, args));
}

const rl = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of rl) {
  if (!line.trim()) continue;
  const request = JSON.parse(line);
  try {
    const result = await callMethod(request.method, request.args || []);
    process.stdout.write(`${JSON.stringify({ id: request.id, ok: true, result })}\n`);
  } catch (error) {
    process.stdout.write(`${JSON.stringify({ id: request.id, ok: false, error: String(error?.message || error) })}\n`);
  }
}
