import https from "node:https";

const url = process.argv[2];
if (!url) throw new Error("usage: node round-61-cdn-speed-probe.mjs URL");

const started = Date.now();
let bytes = 0;
let status = null;
const res = await new Promise((resolve, reject) => {
  https.get(url, { headers: { Range: "bytes=0-16777215" } }, resolve).on("error", reject);
});
status = res.statusCode;
for await (const chunk of res) {
  bytes += chunk.length;
  if (Date.now() - started > 15_000) break;
}
res.destroy();
console.log({
  status,
  bytesIn15s: bytes,
  approxMiBps: Number((bytes / 1048576 / ((Date.now() - started) / 1000)).toFixed(2)),
  contentRange: res.headers["content-range"],
});
