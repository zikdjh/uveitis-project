// Round 9: 390px viewport regression on doctor pages.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector('input[name="username"]', { timeout: 15000 });
await page.fill('input[name="username"]', "doctor");
await page.fill('input[name="password"]', "doctor-dev-2026");
await page.click('button[type="submit"]');
await page.waitForURL("**/doctor/**", { timeout: 20000 });

await page.cdp("Emulation.setDeviceMetricsOverride", {
  width: 390,
  height: 844,
  deviceScaleFactor: 1,
  mobile: true,
});

const targets = [
  "/doctor/workbench",
  "/doctor/cases",
  "/doctor/knowledge",
  "/doctor/security",
];

for (const path of targets) {
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
      actionable: [...document.querySelectorAll("button, a[href]")].filter(visible).length,
      heading: document.querySelector("h1")?.textContent?.trim() ?? null,
      tables: document.querySelectorAll("table").length,
      pagination: !!document.querySelector(".ant-pagination"),
    };
  });
  console.log("MOBILE " + JSON.stringify(metrics));
}

await page.goto("http://127.0.0.1:5173/doctor/cases");
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(900);
await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r09-mobile-cases.png",
});

const caseLinks = await page.evaluate(() =>
  [...document.querySelectorAll('a[href^="/doctor/cases/"]')].map((a) => a.getAttribute("href")),
);
console.log("CASE_LINKS " + JSON.stringify(caseLinks.slice(0, 5)));

await page.cdp("Emulation.clearDeviceMetricsOverride", {});
console.log({ mobileDone: true });
