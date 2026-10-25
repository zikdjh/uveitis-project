const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://www.kaggle.com/datasets/orvile/eye-diseases-classification", { timeout: 60_000 });
await page.waitForLoadState("load", { timeout: 30_000 }).catch(() => {});
await page.click('button:has-text("file_download")');
await page.waitForSelector("text=Download dataset as zip", { timeout: 30_000 });
console.log(await page.evaluate(() =>
  [...document.querySelectorAll("[role=menuitem], li")]
    .map((n) => n.innerText?.trim())
    .filter((t) => t?.includes("Download dataset as zip")),
));
