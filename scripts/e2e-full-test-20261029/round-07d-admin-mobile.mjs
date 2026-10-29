const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");

await page.evaluate(async () => {
  const csrf = document.cookie.split(";").map((c) => c.trim())
    .find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "";
  await fetch("/api/v1/auth/logout", {
    method: "POST", credentials: "include",
    headers: { "X-CSRF-Token": csrf },
  });
});

await page.goto("http://127.0.0.1:5173/admin/login");
await page.waitForSelector("form", { timeout: 10000 });
await page.fill("input[name=password]", "root-20261025");
await page.click("button[type=submit]");
await page.waitForURL("**/admin**", { timeout: 15000 });

await page.cdp("Emulation.setDeviceMetricsOverride", {
  width: 390, height: 844, deviceScaleFactor: 2, mobile: true,
});

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
