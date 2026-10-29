// Round 14: 390px viewport regression on admin pages.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

const paths = [
  "/admin",
  "/admin/cases",
  "/admin/knowledge",
  "/admin/services",
  "/admin/data-dictionary",
  "/admin/access",
  "/admin/security",
];

await page.cdp("Emulation.setDeviceMetricsOverride", {
  width: 390,
  height: 844,
  deviceScaleFactor: 1,
  mobile: true,
});

for (const path of paths) {
  await page.goto("http://127.0.0.1:5173" + path);
  await page.waitForSelector("main", { timeout: 20000 });
  await page.waitForTimeout(900);
  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    const visible = (node) => node.offsetParent !== null;
    return {
      path: location.pathname,
      clientWidth: doc.clientWidth,
      scrollWidth: doc.scrollWidth,
      horizontalOverflow: doc.scrollWidth > doc.clientWidth + 1,
      heading: document.querySelector("h1")?.textContent?.trim() ?? null,
      actionable: [...document.querySelectorAll("button, a[href]")].filter(visible).length,
    };
  });
  console.log("ADMIN_MOBILE " + JSON.stringify(metrics));
}

await page.goto("http://127.0.0.1:5173/admin/access");
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1000);
await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r14-admin-mobile-access.png",
});

await page.cdp("Emulation.clearDeviceMetricsOverride", {});
console.log({ adminMobileDone: true });
