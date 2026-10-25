const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://www.kaggle.com/datasets/linchundan/fundusimage1000", { timeout: 60_000 });
await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
await page.click('button:has-text("file_download")');
await page.waitForSelector("text=Download dataset as zip", { timeout: 30_000 });
console.log(await page.evaluate(() =>
  [...document.querySelectorAll("[role=menuitem], li")]
    .map((n) => n.innerText?.trim())
    .filter((t) => t?.includes("Download dataset as zip")),
));

const downloadPromise = page.waitForEvent("download", { timeout: 180_000 });
await page.click("text=Download dataset as zip");
try {
  const download = await downloadPromise;
  const savePath =
    "D:/temp/gpt/uveitis-project/datasets/p0/kaggle-jsiec1000/" +
    download.suggestedFilename();
  await download.saveAs(savePath);
  console.log({
    savedTo: savePath,
    file: download.suggestedFilename(),
    failure: await download.failure(),
  });
} catch (error) {
  console.log({ error: error.message, url: await page.url() });
  console.log(await page.evaluate(() => document.body.innerText.slice(0, 2000)));
}
