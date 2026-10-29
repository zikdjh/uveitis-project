const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector("form", { timeout: 15000 });
await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]");
await page.waitForURL("**/doctor/workbench", { timeout: 20000 });

const state = await page.evaluate(() => ({
  url: location.pathname,
  heading: document.querySelector("h1")?.textContent?.trim() ?? null,
  cookies: document.cookie
    .split(";")
    .map((item) => item.trim().split("=")[0])
    .filter(Boolean),
}));

console.log({ spaceId: task.spaceId, page: page.label, ...state });
