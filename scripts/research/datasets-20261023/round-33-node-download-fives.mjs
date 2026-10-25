import { createWriteStream } from "node:fs";
import { mkdir } from "node:fs/promises";
import { Readable } from "node:stream";
import { pipeline } from "node:stream/promises";
import { fetch, ProxyAgent } from "undici";

const url = "https://ndownloader.figshare.com/files/34969398";
const outDir = "D:/temp/gpt/uveitis-project/datasets/p0/fives";
const outFile = `${outDir}/FIVES_A_Fundus_Image_Dataset_for_AI_based_Vessel_Segmentation.rar`;

await mkdir(outDir, { recursive: true });
const response = await fetch(url, { dispatcher: new ProxyAgent("http://127.0.0.1:7890") });
if (!response.ok || !response.body) {
  throw new Error(`Download failed: ${response.status} ${response.statusText}`);
}

await pipeline(Readable.fromWeb(response.body), createWriteStream(outFile));
console.log({ status: response.status, savedTo: outFile });
