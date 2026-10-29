// Round 7: doctor UI flow - login, workbench, cases list.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

try {
  const info = await page.cdp("Browser.getWindowForTarget", {});
  await page.cdp("Browser.setWindowBounds", {
    windowId: info.windowId,
    bounds: { windowState: "normal" },
  });
  console.log({ windowRestored: true });
} catch (error) {
  console.log({ windowRestoreError: String(error && error.message) });
}

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector('input[name="username"]', { timeout: 15000 });
await page.fill('input[name="username"]', "doctor");
await page.fill('input[name="password"]', "doctor-dev-2026");
await page.click('button[type="submit"]');
await page.waitForURL("**/doctor/**", { timeout: 20000 });
console.log({ afterLogin: await page.url() });

const workbench = await page.evaluate(() => ({
  path: location.pathname,
  headings: [...document.querySelectorAll("h1, h2, h3")].map((n) => n.textContent.trim()),
  tableRows: document.querySelectorAll("tbody tr").length,
  hasPagination: !!document.querySelector(".ant-pagination"),
  links: [...document.querySelectorAll("a[href]")].map((a) => a.getAttribute("href")).slice(0, 20),
}));
console.log("WORKBENCH " + JSON.stringify(workbench));

await page.goto("http://127.0.0.1:5173/doctor/cases");
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1200);
const cases = await page.evaluate(() => ({
  path: location.pathname,
  headings: [...document.querySelectorAll("h1, h2, h3")].map((n) => n.textContent.trim()),
  tableRows: document.querySelectorAll("tbody tr").length,
  hasPagination: !!document.querySelector(".ant-pagination"),
  emptyText: document.body.innerText.includes("暂无"),
  filters: [...document.querySelectorAll(".ant-select, .ant-picker, input")].length,
}));
console.log("CASES " + JSON.stringify(cases));

const shot = await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r07-doctor-cases.png",
});
console.log({ screenshot: shot });
