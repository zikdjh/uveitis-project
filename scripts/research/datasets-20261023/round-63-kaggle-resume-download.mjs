import { createWriteStream, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import { Transform } from "node:stream";
import https from "node:https";

const { username, key } = JSON.parse(
  readFileSync("D:/temp/gpt/uveitis-project/.kaggle/kaggle.json", "utf8"),
);
const slug = process.argv[2];
const outFile = path.resolve(process.argv[3]);
const expected = process.argv[4] ? Number(process.argv[4]) : null;
if (!slug || !outFile) throw new Error("usage: node round-63-kaggle-resume-download.mjs owner/slug out.zip [expectedBytes]");

mkdirSync(path.dirname(outFile), { recursive: true });
const auth = Buffer.from(`${username}:${key}`).toString("base64");
const sourceUrl = `https://www.kaggle.com/api/v1/datasets/download/${slug}`;
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

function request(url, headers) {
  return new Promise((resolve, reject) => {
    https.get(url, { headers }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        request(new URL(res.headers.location, url).toString(), headers).then(resolve, reject);
        return;
      }
      resolve(res);
    }).on("error", reject);
  });
}

for (let attempt = 1; attempt <= 30; attempt++) {
  const existing = existsSync(outFile) ? statSync(outFile).size : 0;
  if (expected && existing >= expected) {
    console.log(JSON.stringify({ savedTo: outFile, bytes: existing, complete: existing === expected }));
    break;
  }
  const headers = {
    Authorization: `Basic ${auth}`,
    "User-Agent": "kaggle-api/1.8.0",
  };
  if (existing > 0) headers.Range = `bytes=${existing}-`;

  const res = await request(sourceUrl, headers);
  console.log(JSON.stringify({
    attempt,
    status: res.statusCode,
    existing,
    contentLength: res.headers["content-length"],
    contentRange: res.headers["content-range"],
  }));
  if (![200, 206].includes(res.statusCode)) {
    let body = "";
    for await (const chunk of res) body += chunk;
    console.error(`HTTP ${res.statusCode}: ${body.slice(0, 300)}`);
    await sleep(15_000);
    continue;
  }

  const append = res.statusCode === 206 && existing > 0;
  let received = append ? existing : 0;
  let lastLog = Date.now();
  let lastData = Date.now();
  const counter = new Transform({
    transform(chunk, _enc, cb) {
      received += chunk.length;
      lastData = Date.now();
      if (Date.now() - lastLog > 60_000) {
        lastLog = Date.now();
        console.log(`progress ${(received / 1048576).toFixed(1)} MiB`);
      }
      cb(null, chunk);
    },
  });
  const stall = setInterval(() => {
    if (Date.now() - lastData > 120_000) res.destroy(new Error("stalled"));
  }, 15_000);

  try {
    await pipeline(res, counter, createWriteStream(outFile, { flags: append ? "a" : "w" }));
  } catch (error) {
    console.error(`stream failed: ${error.message}`);
  } finally {
    clearInterval(stall);
  }

  const size = existsSync(outFile) ? statSync(outFile).size : 0;
  if (!expected || size === expected) {
    console.log(JSON.stringify({ savedTo: outFile, bytes: size, complete: expected ? size === expected : null }));
    break;
  }
  console.error(`incomplete ${size}/${expected}, retrying`);
  await sleep(15_000);
}
