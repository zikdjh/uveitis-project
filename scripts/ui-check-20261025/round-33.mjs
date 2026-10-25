const task = await taskSpace(8);
const page = task.page("p1");
await page.cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
await page.goto("http://127.0.0.1:5173/doctor/cases/0f7762ec-c7b4-4965-9efb-67cba861f326/report");
await page.waitForSelector(".case-tabs");
console.log(await page.evaluate(() => {
  const overflowing = [...document.querySelectorAll("body *")].filter(n => n.getBoundingClientRect().right > innerWidth + 0.5 || n.getBoundingClientRect().left < -0.5).slice(0, 10).map(n => ({tag:n.tagName, cls:n.className, rect:n.getBoundingClientRect().toJSON()}));
  return {
    viewport: innerWidth + "x" + innerHeight,
    documentWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    viewportWidth: innerWidth,
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    navOverflow: document.querySelector(".app-nav")?.scrollWidth > document.querySelector(".app-nav")?.clientWidth,
    tabsOverflow: document.querySelector(".case-tabs")?.scrollWidth > document.querySelector(".case-tabs")?.clientWidth,
    overflowing,
  };
});
