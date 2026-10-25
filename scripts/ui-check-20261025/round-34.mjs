const task = await taskSpace(8);
const page = task.page("p1");
await page.cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
await page.goto("http://127.0.0.1:5173/doctor/cases/0f7762ec-c7b4-4965-9efb-67cba861f326/report");
await page.waitForSelector(".case-tabs");
const result = await page.evaluate(() => {
  const out = [];
  for (const n of document.body.querySelectorAll("*")) {
    const r = n.getBoundingClientRect();
    if (r.right > innerWidth + 0.5 || r.left < -0.5) {
      out.push({ tag: n.tagName, cls: String(n.className), left: r.left, right: r.right, width: r.width });
      if (out.length === 10) break;
    }
  }
  return {
    innerWidth,
    docWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
    navOverflow: document.querySelector(".app-nav").scrollWidth > document.querySelector(".app-nav").clientWidth,
    tabsOverflow: document.querySelector(".case-tabs").scrollWidth > document.querySelector(".case-tabs").clientWidth,
    overflowing: out,
  };
});
console.log(result);
