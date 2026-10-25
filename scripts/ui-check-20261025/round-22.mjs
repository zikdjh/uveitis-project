const task = await taskSpace(8);
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/doctor/cases/0f7762ec-c7b4-4965-9efb-67cba861f326/analysis");
await page.waitForSelector("button.primary");
console.log(await page.snapshot());
await page.click("button.primary");
await page.waitForSelector("text=分析完成", { timeout: 30000 });
console.log(await page.snapshot());
console.log(await page.evaluate(() => ({ url: location.href, overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth })));
