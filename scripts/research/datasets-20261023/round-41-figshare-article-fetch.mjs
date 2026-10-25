import https from "node:https";
import { writeFileSync } from "node:fs";
import { HttpsProxyAgent } from "https-proxy-agent";

const articleId = process.argv[2];
if (!articleId) throw new Error("usage: node round-41-figshare-article-fetch.mjs <article-id>");

const agent = new HttpsProxyAgent("http://127.0.0.1:7890");

function getJson(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { agent, headers: { Accept: "application/json" } }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        getJson(new URL(res.headers.location, url).toString()).then(resolve, reject);
        return;
      }
      let body = "";
      res.on("data", (chunk) => { body += chunk; });
      res.on("end", () => resolve({ status: res.statusCode, body }));
    }).on("error", reject);
  });
}

const { status, body } = await getJson(`https://api.figshare.com/v2/articles/${articleId}`);
if (status !== 200) {
  throw new Error(`API returned ${status}: ${body.slice(0, 500)}`);
}

const article = JSON.parse(body);
writeFileSync("D:/temp/gpt/uveitis-project/scripts/research/datasets-20261023/round-41-article-" + articleId + ".json", body, "utf8");

console.log(JSON.stringify({
  id: article.id,
  title: article.title,
  files: (article.files ?? []).map((f) => ({ id: f.id, name: f.name, size: f.size, downloadUrl: f.download_url })),
}, null, 2));
