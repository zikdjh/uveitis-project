const task = await taskSpace(8);
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/");
await page.waitForSelector("h1");
const patient = await page.evaluate(() => ({
  viewport: innerWidth + "x" + innerHeight,
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  headerWidth: document.querySelector(".patient-header")?.getBoundingClientRect().width,
  mainWidth: document.querySelector(".patient-main")?.getBoundingClientRect().width,
  navOverflow: document.querySelector(".patient-nav")?.scrollWidth > document.querySelector(".patient-nav")?.clientWidth,
  nav: [...document.querySelectorAll(".patient-nav a")].map(n => ({text:n.textContent,left:n.getBoundingClientRect().left,right:n.getBoundingClientRect().right,w:n.getBoundingClientRect().width})),
  h1: document.querySelector("h1")?.getBoundingClientRect(),
}));
console.log(patient);
