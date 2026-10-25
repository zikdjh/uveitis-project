import { createWriteStream, existsSync, mkdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { pipeline } from "node:stream/promises";
import https from "node:https";

const { username, key } = JSON.parse(
  readFileSync("D:/temp/gpt/uveitis-project/.kaggle/kaggle.json", "utf8"),
);
const ownerSlug = process.argv[2];
const outFile = path.resolve(process.argv[3]);
if (!ownerSlug || !outFile) throw new Error("usage: node round-58-kaggle-api-download.mjs owner/slug out.zip");

mkdirSync(path.dirname(outFile), { recursive: true });
const url = `https://www.kaggle.com/api/v1/datasets/download/${ownerSlug}`;
const auth = Buffer.from(`${username}:${key}`).toString("base64");

function request(url, headers = {}) {
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

const existing = existsSync(outFile) ? statSync(outFile).size : 0;
const headers = {
  Authorization: `Basic ${auth}`,
  "User-Agent": "kaggle-api/1.8.0",
};
if (existing > 0) headers.Range = `bytes=${existing}-`;

const res = await request(url, headers);
console.log({ status: res.statusCode, contentLength: res.headers["content-length"], contentRange: res.headers["content-range"] });
if (![200, 206].includes(res.statusCode)) {
  let body = "";
  for await (const chunk of res) body += chunk;
  throw new Error(`HTTP ${res.statusCode}: ${body.slice(0, 500)}`);
}

const append = res.statusCode === 206;
await pipeline(res, createWriteStream(outFile, { flags: append ? "a" : "w" }));
console.log({ savedTo: outFile, bytes: statSync(outFile).size });
