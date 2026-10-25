import { readFileSync } from "node:fs";
import https from "node:https";

const { username, key } = JSON.parse(
  readFileSync("D:/temp/gpt/uveitis-project/.kaggle/kaggle.json", "utf8"),
);
const auth = Buffer.from(`${username}:${key}`).toString("base64");
const slug = process.argv[2];

function req(url, headers = {}, method = "GET") {
  return new Promise((resolve, reject) => {
    const r = https.request(url, { method, headers }, (res) => {
      let body = "";
      res.on("data", (c) => (body += c));
      res.on("end", () =>
        resolve({ status: res.statusCode, headers: res.headers, body: body.slice(0, 1500) }),
      );
    });
    r.on("error", reject);
    r.end();
  });
}

const headers = { Authorization: `Basic ${auth}`, "User-Agent": "kaggle-api/1.8.0" };
console.log(await req(`https://www.kaggle.com/api/v1/datasets/view/${slug}`, headers));
