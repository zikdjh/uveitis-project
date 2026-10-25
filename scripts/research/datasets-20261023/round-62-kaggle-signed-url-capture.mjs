const fs = await import("node:fs/promises");
const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://www.kaggle.com/datasets/linchundan/fundusimage1000", { timeout: 60_000 });
await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
await page.click('button:has-text("file_download")');
await page.waitForSelector("text=Download dataset as zip", { timeout: 30_000 });
const downloadPromise = page.waitForEvent("download", { timeout: 30_000 });
await page.click("text=Download dataset as zip");
const download = await downloadPromise;
await fs.writeFile(
  "D:/temp/gpt/uveitis-project/.cache/kaggle-jsiec-signed-url.txt",
  download.url(),
  "utf8",
);
console.log({
  saved: true,
  file: download.suggestedFilename(),
  urlLength: download.url().length,
});
