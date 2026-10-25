import { mkdir } from "node:fs/promises";

const task = await taskSpace("uveitis figshare downloads 20261024");
const page = task.page("p1");
const outDir = "D:/temp/gpt/uveitis-project/datasets/p0/fives";
const outFile = `${outDir}/FIVES_A_Fundus_Image_Dataset_for_AI_based_Vessel_Segmentation.rar`;

await mkdir(outDir, { recursive: true });
const downloadPromise = page.waitForEvent("download", { timeout: 600_000 });
await page.goto("https://ndownloader.figshare.com/files/34969398", { timeout: 45_000 }).catch(() => null);
const download = await downloadPromise;
await download.saveAs(outFile);
console.log({
  suggestedFilename: download.suggestedFilename(),
  savedTo: outFile,
});
