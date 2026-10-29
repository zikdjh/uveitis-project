// Round 5: log into the admin console via the real UI, then open services page.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

await page.waitForSelector('input[name="password"]', { timeout: 15000 });
await page.fill('input[name="username"]', "root");
await page.fill('input[name="password"]', "root-20261025");
await page.click("loc=role:button[name='进入管理后台']");

await page.waitForFunction(
  () => location.pathname.startsWith("/admin") && !location.pathname.startsWith("/admin/login"),
  undefined,
  { timeout: 20000 },
);
console.log({ afterLogin: await page.url() });

await page.goto("http://127.0.0.1:5173/admin/services");
await page.waitForSelector("#summary-api", { timeout: 20000 });

const state = await page.evaluate(() => ({
  url: location.pathname,
  cookies: document.cookie
    .split(";")
    .map((item) => item.trim().split("=")[0])
    .filter(Boolean),
  headings: [...document.querySelectorAll("h1, h2, h3")].map((n) => n.textContent.trim()).slice(0, 20),
}));
console.log("STATE " + JSON.stringify(state));
console.log(await page.snapshot({ scope: "full_page" }));
