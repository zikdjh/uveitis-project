const task = await taskSpace("uveitis-doctor-patient-ui-20261025");
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/");
await page.waitForSelector("h1");
console.log("space=" + task.spaceId);
console.log("url=" + await page.url());
console.log(await page.snapshot({ scope: "full_page" }));
await page.screenshot({ path: "D:/temp/gpt/uveitis-project/scripts/ui-check-20261025/patient-home-desktop.png" });
