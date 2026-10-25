const task = await taskSpace(8);
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/login");
const response = await page.fetch("/api/v1/auth/login", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ username: "doctor", password: "doctor-dev-2026" }),
});
console.log({ loginStatus: response.status, loginBody: response.body });
await page.goto("http://127.0.0.1:5173/doctor/workbench");
await page.waitForSelector("text=工作台");
console.log("url=" + await page.url());
console.log(await page.snapshot());
await page.screenshot({ path: "D:/temp/gpt/uveitis-project/scripts/ui-check-20261025/doctor-workbench-desktop.png" });
