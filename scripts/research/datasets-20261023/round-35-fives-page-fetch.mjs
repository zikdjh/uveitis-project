import { mkdir } from "node:fs/promises";

const task = await taskSpace("uveitis figshare downloads 20261024");
const page = task.page("p1");
const outDir = "D:/temp/gpt/uveitis-project/datasets/p0/fives";
const outFile = `${outDir}/FIVES_A_Fundus_Image_Dataset_for_AI_based_Vessel_Segmentation.rar`;

await mkdir(outDir, { recursive: true });
const response = await page.fetch("https://springernature.figshare.com/ndownloader/files/34969398", {
  saveAs: outFile,
  timeout: 600_000,
});
console.log({ status: response.status, ok: response.ok, savedTo: outFile });
