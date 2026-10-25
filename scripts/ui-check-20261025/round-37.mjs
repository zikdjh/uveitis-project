const task = await taskSpace(8);
const page = task.page("p1");
await page.evaluate(async () => { await fetch("/api/v1/auth/logout", { method: "POST" }); });
await page.goto("http://127.0.0.1:5173/doctor/workbench");
await page.waitForURL("**/login");
console.log("finalAuthRedirect=" + await page.url());
await page.evaluate(async () => {
  await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "doctor", password: "doctor-dev-2026" }),
  });
});
await page.goto("http://127.0.0.1:5173/doctor/workbench");
await page.waitForSelector("h1:has-text('工作台')");
const doctor = await page.evaluate(() => ({ url: location.href, overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth }));
await page.goto("http://127.0.0.1:5173/admin");
await page.waitForURL("**/forbidden");
const forbidden = await page.url();
console.log({ doctor: doctor, doctorAdminAccess: forbidden });
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
console.log(await page.evaluate(() => ({
  adminUrl: location.href,
  services: [...document.querySelectorAll(".service-card")].map(n => n.textContent.trim()),
  modelText: document.querySelector(".boundary-list")?.textContent,
  overflowX: document.documentElement.scrollWidth > document.documentElement.clientWidth,
})));
await task.finish({ keep: [] });
