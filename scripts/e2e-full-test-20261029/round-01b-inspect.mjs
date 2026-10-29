const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/doctor/cases");
await page.waitForTimeout(2000);
const text = await page.evaluate(() => document.body.innerText.slice(0, 600));
console.log({ url: await page.url(), text });
