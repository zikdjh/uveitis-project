// Round 17b: restore the browser window and capture the B-01 analysis page.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");
const CASE_ID = "47bd1e4c-39c9-48d0-9980-bbbbb4b0e451";

let windowRestore = "skipped";
try {
  const handle = await page.cdp("Browser.getWindowForTarget");
  await page.cdp("Browser.setWindowBounds", {
    windowId: handle.windowId,
    bounds: { windowState: "normal" },
  });
  windowRestore = `ok windowId=${handle.windowId}`;
} catch (reason) {
  windowRestore = `failed: ${reason.message}`;
}

await page.goto(`http://127.0.0.1:5173/doctor/cases/${CASE_ID}/analysis`);
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1200);

let shot = null;
try {
  shot = await page.screenshot({
    path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r17-real-model.png",
  });
} catch (reason) {
  shot = `screenshot-skipped: ${reason.message}`;
}

console.log(JSON.stringify({ round: "17b", windowRestore, shot }, null, 2));
