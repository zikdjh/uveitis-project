const task = await taskSpace(8);
const page = task.page("p1");
await page.evaluate(() => {
  globalThis.__errors = [];
  addEventListener("error", e => globalThis.__errors.push("error:" + e.message));
  addEventListener("unhandledrejection", e => globalThis.__errors.push("rejection:" + String(e.reason)));
});
await page.goto("http://127.0.0.1:5173/login");
await page.waitForTimeout(300);
await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]");
await page.waitForTimeout(1000);
console.log(await page.evaluate(() => ({ url: location.href, root: document.getElementById("root")?.innerHTML, errors: globalThis.__errors })));
