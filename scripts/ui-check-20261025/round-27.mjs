const task = await taskSpace(8);
const page = task.page("p1");
await page.evaluate(async () => {
  await fetch("/api/v1/auth/logout", { method: "POST" });
  await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "admin", password: "admin-dev-2026" }),
  });
});
await page.goto("http://127.0.0.1:5173/admin/services");
await page.waitForSelector("h1:has-text('服务状态')");
console.log(await page.snapshot());
console.log(await page.evaluate(() => ({
  url: location.href,
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
  serviceCards: document.querySelectorAll(".service-card").length,
})));
