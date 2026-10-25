const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://www.kaggle.com/datasets/kondwani/eye-disease-dataset", { timeout: 60_000 });
await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});

await page.click('button:has-text("file_download")');
await page.waitForSelector("text=Download dataset as zip", { timeout: 30_000 });
const txt = await page.evaluate(() =>
  [...document.querySelectorAll("li, [role=menuitem]")]
    .map((n) => n.innerText?.trim())
    .filter((t) => t?.includes("Download dataset as zip")),
);
console.log({ menuItems: txt });

const downloadPromise = page.waitForEvent("download", { timeout: 120_000 });
await page.click("text=Download dataset as zip");
try {
  const download = await downloadPromise;
  console.log({ url: download.url(), file: download.suggestedFilename() });
  await download.saveAs(
    "D:/temp/gpt/uveitis-project/datasets/p0/kaggle-eye-disease-kondwani/" +
      download.suggestedFilename(),
  );
  console.log({ saved: true, failure: await download.failure() });
} catch (error) {
  console.log({ error: error.message, url: await page.url() });
  const text = await page.evaluate(() => document.body.innerText.slice(0, 3000));
  console.log(text);
}
