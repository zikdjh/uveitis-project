const task = await taskSpace(8);
const page = task.page("p1");
const metrics = await page.evaluate(() => ({
  viewport: { width: innerWidth, height: innerHeight },
  title: document.querySelector("h1")?.textContent,
  grid: getComputedStyle(document.querySelector(".workbench-grid")).gridTemplateColumns,
  cards: [...document.querySelectorAll(".metric-card")].map(n => ({w: n.getBoundingClientRect().width, h: n.getBoundingClientRect().height})),
  panelWidths: [...document.querySelectorAll(".workbench-grid > .panel")].map(n => n.getBoundingClientRect().width),
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  buttons: [...document.querySelectorAll("button")].map(n => n.textContent.trim()),
}));
console.log(metrics);
const caseHref = await page.evaluate(() => document.querySelector(".case-table a")?.getAttribute("href"));
await page.goto("http://127.0.0.1:5173" + caseHref);
await page.waitForSelector(".case-tabs");
console.log(await page.snapshot());
console.log(await page.evaluate(() => ({
  url: location.href,
  h1: document.querySelector("h1")?.textContent,
  tabs: [...document.querySelectorAll(".case-tabs a")].map(n => n.textContent),
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  tabWidths: [...document.querySelectorAll(".case-tabs a")].map(n => n.getBoundingClientRect().width),
})));
