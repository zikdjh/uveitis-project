const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector("form", { timeout: 10000 });
await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]");
await page.waitForURL("**/doctor/workbench", { timeout: 15000 });
console.log({ login: "ok", url: await page.url() });

await page.goto("http://127.0.0.1:5173/doctor/cases");
await page.waitForSelector("button", { timeout: 10000 });

const createButton = await page.evaluate(() => {
  const buttons = [...document.querySelectorAll("button")];
  const match = buttons.find((b) => b.textContent.includes("新建"));
  return match ? match.textContent : null;
});
console.log({ createButton });
