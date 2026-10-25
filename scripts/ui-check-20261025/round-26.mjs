const task = await taskSpace(8);
const page = task.page("p1");
await page.fill("@105", "眼红眼痛畏光需要检查吗");
await page.click("@106");
await page.waitForSelector(".knowledge-results article", { timeout: 30000 });
console.log(await page.snapshot());
console.log(await page.evaluate(() => ({ url: location.href, overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth, resultCount: document.querySelectorAll(".knowledge-results article").length, result: document.querySelector(".knowledge-results")?.textContent })));
