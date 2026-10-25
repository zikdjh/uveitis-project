const task = await taskSpace(8);
const page = task.page("p1");
await page.cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
await page.goto("http://127.0.0.1:5173/doctor/cases/0f7762ec-c7b4-4965-9efb-67cba861f326/report");
await page.waitForSelector(".app-nav");
await page.waitForTimeout(300);
const result = await page.evaluate(() => {
  const nav = document.querySelector(".app-nav");
  const nr = nav.getBoundingClientRect();
  const links = [];
  for (const n of nav.querySelectorAll("a")) {
    const r = n.getBoundingClientRect();
    links.push({ text: n.textContent.trim(), left: r.left, right: r.right, width: r.width });
  }
  const tabs = document.querySelector(".case-tabs");
  return {
    innerWidth: innerWidth,
    docWidth: document.documentElement.scrollWidth,
    navWidth: nr.width,
    navScrollWidth: nav.scrollWidth,
    navClientWidth: nav.clientWidth,
    navOverflow: nav.scrollWidth > nav.clientWidth,
    links: links,
    tabsOverflow: tabs.scrollWidth > tabs.clientWidth,
    overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  };
});
console.log(result);
