const task = await taskSpace(8);
const page = task.page("p1");
await page.cdp("Emulation.setDeviceMetricsOverride", { width: 390, height: 844, deviceScaleFactor: 1, mobile: true });
await page.goto("http://127.0.0.1:5173/");
await page.waitForSelector("h1");
console.log(await page.info());
console.log(await page.evaluate(() => ({
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  header: document.querySelector(".patient-header")?.getBoundingClientRect().toJSON(),
  nav: document.querySelector(".patient-nav")?.getBoundingClientRect().toJSON(),
  navOverflow: document.querySelector(".patient-nav")?.scrollWidth > document.querySelector(".patient-nav")?.clientWidth,
  links: [...document.querySelectorAll(".patient-nav a")].map(n => ({text:n.textContent.trim(),w:n.getBoundingClientRect().width,right:n.getBoundingClientRect().right})),
  main: document.querySelector(".patient-main")?.getBoundingClientRect().toJSON(),
  intro: document.querySelector(".patient-intro")?.getBoundingClientRect().toJSON(),
  h1: document.querySelector(".patient-intro h1")?.getBoundingClientRect().toJSON(),
  patientGrid: document.querySelector(".patient-grid") ? getComputedStyle(document.querySelector(".patient-grid")).gridTemplateColumns : null,
})));
