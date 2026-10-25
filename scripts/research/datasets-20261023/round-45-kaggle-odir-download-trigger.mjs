const task = await takeOverTaskSpace(2);
const page = task.page("p1");

await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});

const downloadPromise = page.waitForEvent("download", { timeout: 120_000 });
const candidates = await page.evaluate(() =>
  [...document.querySelectorAll("button")]
    .filter((node) => node.textContent?.includes("Download"))
    .map((node, index) => ({
      index,
      text: node.textContent?.trim().replace(/\s+/g, " "),
      inMain: Boolean(node.closest("main")),
      ariaLabel: node.getAttribute("aria-label"),
      className: node.className?.toString().slice(0, 120),
    })),
);
console.log({ candidates });

const receipt = await page.click('button:has-text("file_download")');
console.log({ clickReceipt: receipt });

try {
  const download = await downloadPromise;
  console.log({
    downloadUrl: download.url(),
    suggestedFilename: download.suggestedFilename(),
  });
} catch (error) {
  console.log({
    downloadWaitError: error.message,
    currentUrl: await page.url(),
    currentTitle: await page.title(),
  });
  console.log(await page.snapshot());
}
