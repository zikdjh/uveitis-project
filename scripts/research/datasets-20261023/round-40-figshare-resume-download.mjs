import { createWriteStream, existsSync, mkdirSync, rmSync, statSync } from "node:fs";
import { pipeline } from "node:stream/promises";
import { Transform } from "node:stream";
import { parseArgs } from "node:util";
import path from "node:path";
import https from "node:https";
import { HttpsProxyAgent } from "https-proxy-agent";

const { values } = parseArgs({
  options: {
    url: { type: "string" },
    out: { type: "string" },
    expected: { type: "string" },
  },
});

if (!values.url || !values.out) {
  throw new Error("usage: node round-40-figshare-resume-download.mjs --url <ndownloader-url> --out <file> [--expected <bytes>]");
}

const proxy = "http://127.0.0.1:7890";
const agent = new HttpsProxyAgent(proxy);
const expectedBytes = values.expected ? Number(values.expected) : null;
const outFile = path.resolve(values.out);
mkdirSync(path.dirname(outFile), { recursive: true });

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";
const MAX_NETWORK_RETRIES = 40;
const MAX_PENDING_ATTEMPTS = 40;
const RETRY_DELAY_MS = 15_000;
const STALL_TIMEOUT_MS = 90_000;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function get(url, headers = {}) {
  return new Promise((resolve, reject) => {
    https.get(url, { agent, headers }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        console.error(`redirect ${res.statusCode} -> ${res.headers.location}`);
        res.resume();
        get(new URL(res.headers.location, url).toString(), headers).then(resolve, reject);
        return;
      }
      resolve(res);
    }).on("error", reject);
  });
}

function readBody(res, limit = 2000) {
  return new Promise((resolve) => {
    let body = "";
    res.on("data", (chunk) => {
      body += chunk;
      if (body.length >= limit) res.destroy();
    });
    res.on("end", () => resolve(body));
    res.on("close", () => resolve(body));
  });
}

async function getWithPendingRetry(url, headers) {
  for (let attempt = 1; attempt <= MAX_PENDING_ATTEMPTS; attempt++) {
    const res = await get(url, headers);
    if (res.statusCode === 202) {
      const retryAfterSec = Number(res.headers["retry-after"]) || 90;
      const body = await readBody(res);
      console.error(`202 pending (attempt ${attempt}/${MAX_PENDING_ATTEMPTS}), retry in ${retryAfterSec}s: ${body.slice(0, 200)}`);
      await sleep(retryAfterSec * 1000);
      continue;
    }
    return res;
  }
  throw new Error(`still 202 pending after ${MAX_PENDING_ATTEMPTS} attempts`);
}

function currentBytes() {
  if (!existsSync(outFile)) return 0;
  return statSync(outFile).size;
}

async function downloadOnce() {
  let existingBytes = currentBytes();
  if (expectedBytes && existingBytes > expectedBytes) {
    rmSync(outFile);
    existingBytes = 0;
  }
  if (expectedBytes && existingBytes === expectedBytes) return;

  const headers = { "User-Agent": USER_AGENT };
  let append = false;
  if (existingBytes > 0) {
    headers.Range = `bytes=${existingBytes}-`;
    append = true;
  }

  const startedAt = Date.now();
  const response = await getWithPendingRetry(values.url, headers);

  if (append && response.statusCode === 200) {
    console.error("server ignored Range header, restarting from scratch");
    append = false;
    existingBytes = 0;
  } else if (response.statusCode === 206) {
    const contentRange = response.headers["content-range"] ?? "";
    if (!contentRange.startsWith(`bytes ${existingBytes}-`)) {
      console.error(`unexpected content-range "${contentRange}", restarting from scratch`);
      append = false;
      existingBytes = 0;
    }
  } else if (response.statusCode === 416) {
    const size = currentBytes();
    if (expectedBytes && size === expectedBytes) return;
    throw new Error(`416 range not satisfiable with local size ${size}`);
  } else if (response.statusCode !== 200) {
    throw new Error(`Download failed with status ${response.statusCode}`);
  }

  let received = existingBytes;
  let lastLogged = Date.now();
  let lastDataAt = Date.now();
  const counter = new Transform({
    transform(chunk, _enc, cb) {
      received += chunk.length;
      lastDataAt = Date.now();
      if (Date.now() - lastLogged >= 60_000) {
        lastLogged = Date.now();
        const pct = expectedBytes ? `${((received / expectedBytes) * 100).toFixed(1)}%` : "unknown";
        const elapsedMin = ((Date.now() - startedAt) / 60_000).toFixed(1);
        console.log(`progress ${pct} ${(received / 1048576).toFixed(0)} MiB ${elapsedMin} min`);
      }
      cb(null, chunk);
    },
  });

  const stall = setInterval(() => {
    if (Date.now() - lastDataAt > STALL_TIMEOUT_MS) {
      response.destroy(new Error(`stalled: no data for 90s at ${received} bytes`));
    }
  }, 15_000);

  try {
    await pipeline(response, counter, createWriteStream(outFile, { flags: append ? "a" : "w" }));
  } finally {
    clearInterval(stall);
  }

  const finalSize = statSync(outFile).size;
  if (expectedBytes) {
    if (finalSize > expectedBytes) {
      rmSync(outFile);
      throw new Error(`oversize ${finalSize} > ${expectedBytes}, restarting`);
    }
    if (finalSize < expectedBytes) {
      throw new Error(`incomplete: ${finalSize}/${expectedBytes}`);
    }
  }
  console.log(JSON.stringify({
    status: response.statusCode,
    savedTo: outFile,
    size: finalSize,
    expectedBytes,
    complete: true,
    elapsedMin: Number(((Date.now() - startedAt) / 60_000).toFixed(1)),
  }));
}

for (let attempt = 1; ; attempt++) {
  try {
    await downloadOnce();
    const finalSize = currentBytes();
    console.log(JSON.stringify({
      savedTo: outFile,
      size: finalSize,
      expectedBytes,
      complete: expectedBytes ? finalSize === expectedBytes : true,
    }));
    break;
  } catch (err) {
    if (attempt >= MAX_NETWORK_RETRIES) throw err;
    console.error(`attempt ${attempt} failed (${err.message}); resume retry in ${RETRY_DELAY_MS / 1000}s`);
    await sleep(RETRY_DELAY_MS);
  }
}
