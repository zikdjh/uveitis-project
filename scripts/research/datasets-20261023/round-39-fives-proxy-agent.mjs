import { createWriteStream, mkdirSync } from "node:fs";
import { mkdir } from "node:fs/promises";
import { pipeline } from "node:stream/promises";
import https from "node:https";
import { HttpsProxyAgent } from "https-proxy-agent";

const proxy = "http://127.0.0.1:7890";
const agent = new HttpsProxyAgent(proxy);
const outDir = "D:/temp/gpt/uveitis-project/datasets/p0/fives";
const outFile = `${outDir}/FIVES_A_Fundus_Image_Dataset_for_AI_based_Vessel_Segmentation.rar`;

async function get(url) {
  return new Promise((resolve, reject) => {
    https.get(url, { agent }, (res) => {
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        res.resume();
        get(new URL(res.headers.location, url).toString()).then(resolve, reject);
        return;
      }
      resolve(res);
    }).on("error", reject);
  });
}

await mkdir(outDir, { recursive: true });
const response = await get("https://ndownloader.figshare.com/files/34969398");
if (response.statusCode !== 200) {
  throw new Error(`Download failed with status ${response.statusCode}`);
}

await pipeline(response, createWriteStream(outFile));
console.log({ status: response.statusCode, savedTo: outFile });
