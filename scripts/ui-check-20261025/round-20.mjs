const task = await taskSpace(8);
const page = task.page("p1");
const caseId = location.pathname.split("/")[3];
await page.goto("http://127.0.0.1:5173/doctor/cases/" + caseId + "/analysis");
await page.click("button.primary");
await page.waitForSelector("text=分析完成", { timeout: 30000 });
console.log(await page.snapshot());
console.log(await page.evaluate(() => ({ url: location.href, overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth, text: document.querySelector("section")?.textContent })));
