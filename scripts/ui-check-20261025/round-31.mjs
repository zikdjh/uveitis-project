const task = await taskSpace(8);
const page = task.page("p1");
await page.evaluate(async () => {
  await fetch("/api/v1/auth/logout", { method: "POST" });
  await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "doctor", password: "doctor-dev-2026" }),
  });
});
await page.goto("http://127.0.0.1:5173/doctor/cases/0f7762ec-c7b4-4965-9efb-67cba861f326/report");
await page.waitForSelector(".case-tabs");
console.log(await page.evaluate(() => ({
  viewport: innerWidth + "x" + innerHeight,
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  sidebar: document.querySelector(".sidebar")?.getBoundingClientRect().toJSON(),
  nav: document.querySelector(".app-nav")?.getBoundingClientRect().toJSON(),
  navOverflow: document.querySelector(".app-nav")?.scrollWidth > document.querySelector(".app-nav")?.clientWidth,
  appMain: document.querySelector(".app-main")?.getBoundingClientRect().toJSON(),
  caseTabs: document.querySelector(".case-tabs")?.getBoundingClientRect().toJSON(),
  tabsOverflow: document.querySelector(".case-tabs")?.scrollWidth > document.querySelector(".case-tabs")?.clientWidth,
  header: document.querySelector(".case-detail-header")?.getBoundingClientRect().toJSON(),
  report: document.querySelector(".case-report")?.getBoundingClientRect().toJSON(),
  overlaps: (() => {
    const a = document.querySelector(".case-tabs")?.getBoundingClientRect();
    const b = document.querySelector(".case-detail-header")?.getBoundingClientRect();
    return a && b ? a.top < b.bottom : null;
  })(),
})));
