const task = await taskSpace(8);
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/doctor/cases/new");
await page.waitForSelector("h1:has-text('新建病例')");
console.log(await page.snapshot());
console.log(await page.evaluate(() => ({ overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth, formWidth: document.querySelector("form")?.getBoundingClientRect().width })));
