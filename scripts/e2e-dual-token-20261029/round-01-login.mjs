const task = await taskSpace("dual token browser verification 20261029");
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector("form", { timeout: 10000 });

await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]");

await page.waitForURL("**/doctor/workbench", { timeout: 15000 });

const cookies = await page.cdp("Network.getCookies", {
  urls: ["http://127.0.0.1:5173", "http://127.0.0.1:8000"],
});
const names = cookies.cookies.map((c) => c.name).sort();

console.log({
  url: page.url(),
  cookies: names,
  hasAccess: names.includes("uveitis_access"),
  hasRefresh: names.includes("uveitis_refresh"),
  hasCsrf: names.includes("uveitis_csrf"),
});
