// Round 13: admin overview and audit surfaces at desktop viewport.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/admin/login");
await page.waitForSelector('input[name="password"]', { timeout: 15000 });
await page.fill('input[name="password"]', "root-20261025");
await page.click("loc=role:button[name='进入管理后台']");
await page.waitForFunction(
  () => location.pathname.startsWith("/admin") && !location.pathname.startsWith("/admin/login"),
  undefined,
  { timeout: 20000 },
);

for (const path of ["/admin", "/admin/security", "/admin/access"]) {
  await page.goto("http://127.0.0.1:5173" + path);
  await page.waitForSelector("main", { timeout: 20000 });
  await page.waitForTimeout(1200);
  const facts = await page.evaluate(() => {
    const main = document.querySelector("main");
    return {
      path: location.pathname,
      heading: document.querySelector("h1")?.textContent?.trim() ?? null,
      subHeadings: [...document.querySelectorAll("h2, h3")].map((n) => n.textContent.trim()).slice(0, 12),
      rows: document.querySelectorAll("tbody tr").length,
      pagination: !!document.querySelector(".ant-pagination"),
      text: (main?.innerText ?? "").replace(/\n{2,}/g, "\n").slice(0, 900),
    };
  });
  console.log("ADMIN " + JSON.stringify(facts));
}

await page.goto("http://127.0.0.1:5173/admin");
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1200);
await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r13-admin-overview.png",
});

console.log({ adminAuditDone: true });
