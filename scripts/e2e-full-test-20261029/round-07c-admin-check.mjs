const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");

await page.cdp("Emulation.setDeviceMetricsOverride", {
  width: 390, height: 844, deviceScaleFactor: 2, mobile: true,
});

await page.goto("http://127.0.0.1:5173/admin");
await page.waitForTimeout(2000);
console.log({ url: await page.url() });

const adminPages = [
  "http://127.0.0.1:5173/admin",
  "http://127.0.0.1:5173/admin/services",
  "http://127.0.0.1:5173/admin/access",
  "http://127.0.0.1:5173/admin/knowledge",
];

const results = [];
for (const url of adminPages) {
  await page.goto(url);
  await page.waitForTimeout(1200);
  const check = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth > window.innerWidth + 2,
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    buttonCount: [...document.querySelectorAll("button")].filter((b) => b.getBoundingClientRect().width > 0).length,
  }));
  results.push({ page: url.split("/").pop() || "dashboard", ...check });
}

console.log(results);
await page.cdp("Emulation.clearDeviceMetricsOverride");
