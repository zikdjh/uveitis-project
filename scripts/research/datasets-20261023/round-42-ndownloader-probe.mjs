import https from "node:https";
import { parseArgs } from "node:util";
import { HttpsProxyAgent } from "https-proxy-agent";

const { values } = parseArgs({ options: { url: { type: "string" } } });
if (!values.url) throw new Error("usage: node round-42-ndownloader-probe.mjs --url <ndownloader-url>");

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36";

function probe(url, agent, label, maxHops = 6) {
  return new Promise((resolve) => {
    https.get(url, { agent, headers: { "User-Agent": UA } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location && maxHops > 0) {
        res.resume();
        probe(new URL(res.headers.location, url).toString(), agent, label, maxHops - 1).then(resolve);
        return;
      }
      res.resume();
      resolve({ label, status: res.statusCode, contentType: res.headers["content-type"] ?? "", contentLength: res.headers["content-length"] ?? "" });
    }).on("error", (err) => resolve({ label, error: err.message }));
  });
}

const proxyResult = await probe(values.url, new HttpsProxyAgent("http://127.0.0.1:7890"), "proxy");
const directResult = await probe(values.url, undefined, "direct").catch((err) => ({ label: "direct", error: err.message }));
console.log(JSON.stringify([proxyResult, directResult], null, 2));
