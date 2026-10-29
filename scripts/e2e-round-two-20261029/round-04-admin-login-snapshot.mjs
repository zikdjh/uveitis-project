// Round 4: restore window (best effort) and snapshot the admin login page.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

try {
  const info = await task.cdp("Browser.getWindowForTarget", {});
  console.log({ windowInfo: info });
  await task.cdp("Browser.setWindowBounds", {
    windowId: info.windowId,
    bounds: { windowState: "normal" },
  });
  console.log({ windowRestored: true });
} catch (error) {
  console.log({ windowRestoreError: String(error && error.message) });
}

await page.waitForSelector("form", { timeout: 15000 });
console.log({ url: await page.url(), title: await page.title() });
console.log(await page.snapshot());
