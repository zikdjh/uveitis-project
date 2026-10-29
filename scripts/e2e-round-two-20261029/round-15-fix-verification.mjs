// Round 15: verify D-02 (protocol label) and D-03 (h1 headings) in the UI.
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

const inspect = async (path) => {
  await page.goto("http://127.0.0.1:5173" + path);
  await page.waitForSelector("main", { timeout: 20000 });
  await page.waitForTimeout(1100);
  const facts = await page.evaluate(() => ({
    path: location.pathname,
    h1: [...document.querySelectorAll("h1")].map((node) => node.textContent.trim()),
    h2Count: document.querySelectorAll("h2").length,
    doc: document.documentElement.scrollWidth > document.documentElement.clientWidth + 1,
  }));
  console.log("CHECK " + JSON.stringify(facts));
};

await inspect("/admin");
await inspect("/admin/services");
await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r15-services-h1.png",
});
await inspect("/admin/data-dictionary");
await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r15-dictionary-h1.png",
});

await page.goto("http://127.0.0.1:5173/admin");
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1100);
const summaryRow = await page.evaluate(() => {
  const nodes = [...document.querySelectorAll("li, tr, div")];
  const hit = nodes.find((node) => node.textContent.includes("外部总结"));
  return hit ? hit.textContent.replace(/\s+/g, " ").trim().slice(0, 120) : null;
});
console.log("SUMMARY_ROW " + JSON.stringify(summaryRow));

console.log({ round15Done: true });
