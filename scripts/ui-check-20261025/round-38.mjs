const task = await taskSpace("uveitis-final-check-20261025");
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/forbidden");
await page.waitForSelector(".status-page h1");
const forbidden = await page.evaluate(() => ({
  title: document.querySelector(".status-page h1")?.textContent,
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  card: document.querySelector(".status-page > div")?.getBoundingClientRect().toJSON(),
}));
console.log({ forbidden });
await task.finish({ keep: [] });
