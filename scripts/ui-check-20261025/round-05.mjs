const task = await taskSpace(8);
const page = task.page("p1");
console.log("url=" + await page.url());
console.log(await page.snapshot());
await page.screenshot({ path: "D:/temp/gpt/uveitis-project/scripts/ui-check-20261025/doctor-current.png" });
