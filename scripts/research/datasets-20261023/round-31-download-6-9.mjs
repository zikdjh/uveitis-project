import { mkdir } from "node:fs/promises";

const task = await taskSpace("uveitis figshare downloads 20261024");
const page = task.page("p1");

const jobs = [
  {
    label: "SUSTech-SYSU metadata json",
    url: "https://ndownloader.figshare.com/files/22543034",
    dir: "D:/temp/gpt/uveitis-project/datasets/p0/sustech-sysu-metadata",
    file: "data.json",
  },
  {
    label: "SUSTech-SYSU metadata csv",
    url: "https://ndownloader.figshare.com/files/22543037",
    dir: "D:/temp/gpt/uveitis-project/datasets/p0/sustech-sysu-metadata",
    file: "metadata_summary.csv",
  },
  {
    label: "FIVES",
    url: "https://ndownloader.figshare.com/files/34969398",
    dir: "D:/temp/gpt/uveitis-project/datasets/p0/fives",
    file: "FIVES_A_Fundus_Image_Dataset_for_AI_based_Vessel_Segmentation.rar",
  },
  {
    label: "Uveitis_All_2025_Oct",
    url: "https://ndownloader.figshare.com/files/58646629",
    dir: "D:/temp/gpt/uveitis-project/datasets/p0/uveitis-all-2025-oct",
    file: "scd.Azimuth.rds",
  },
  {
    label: "Open UWF 700",
    url: "https://ndownloader.figshare.com/files/49014559",
    dir: "D:/temp/gpt/uveitis-project/datasets/p0/open-uwf-700",
    file: "Dataset.zip",
  },
];

for (const job of jobs) {
  await mkdir(job.dir, { recursive: true });
  const outFile = `${job.dir}/${job.file}`;
  const downloadPromise = page.waitForEvent("download", { timeout: 120_000 });
  await page.goto(job.url, { timeout: 45_000 }).catch(() => null);
  const download = await downloadPromise;
  await download.saveAs(outFile);
  console.log({
    label: job.label,
    suggestedFilename: download.suggestedFilename(),
    savedTo: outFile,
  });
}
