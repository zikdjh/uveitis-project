// Round 8: re-enter admin console and capture the services configuration page.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/admin/login");
await page.waitForSelector('input[name="password"]', { timeout: 15000 });
await page.fill('input[name="password"]', "root-20261025");
await page.click("loc=role:button[name='进入管理后台']");
await page.waitForFunction(
  () => location.pathname.startsWith("/admin") && !location.pathname.startsWith("/admin/login"),
  undefined,
  { timeout: 20000 },
);

await page.goto("http://127.0.0.1:5173/admin/services");
await page.waitForSelector("#summary-api", { timeout: 20000 });
await page.waitForTimeout(1000);

const facts = await page.evaluate(() => {
  const text = (selector) => document.querySelector(selector)?.textContent?.trim() ?? null;
  return {
    path: location.pathname,
    providerRows: document.querySelectorAll("article.provider-row").length,
    hasProviderPagination: !!document.querySelector(".ant-pagination"),
    summaryProtocol: text("#summary-api .ant-select-selection-item"),
    summaryBaseUrl: document.querySelector('#summary-api input[type="text"], #summary-api input:not([type])')?.value ?? null,
    searchToggle: text("#search-api .ant-switch"),
    buttons: [...document.querySelectorAll("button")].map((b) => b.textContent.trim()).filter(Boolean).slice(0, 30),
  };
});
console.log("FACTS " + JSON.stringify(facts));

await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r08-admin-services.png",
  fullPage: false,
});
console.log({ screenshot: "shot-r08-admin-services.png" });
