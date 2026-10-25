const task = await taskSpace("uveitis figshare downloads 20261024");
const page = task.page("p1");
const outDir = "D:/temp/gpt/uveitis-project/datasets/p0/fives";

await page.goto("https://springernature.figshare.com/", { timeout: 45_000 }).catch(() => null);
await page.waitForLoadState("load").catch(() => null);

await page.cdp("Browser.setDownloadBehavior", {
  behavior: "allow",
  downloadPath: outDir,
  eventsEnabled: true,
});

await page.evaluate(() => {
  const link = document.createElement("a");
  link.href = "https://springernature.figshare.com/ndownloader/files/34969398";
  link.download = "FIVES_A_Fundus_Image_Dataset_for_AI_based_Vessel_Segmentation.rar";
  document.body.appendChild(link);
  link.click();
  link.remove();
});

await page.waitForTimeout(10_000);
console.log({ outDir });
