// Round 16: confirm the overview shows the configured summary model name.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/admin");
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1200);

const services = await page.evaluate(() => {
  const rows = [...document.querySelectorAll("li, tr")].filter((node) =>
    /（可选）|向量数据库/.test(node.textContent),
  );
  return rows.map((node) => node.textContent.replace(/\s+/g, " ").trim()).slice(0, 8);
});
console.log("SERVICES " + JSON.stringify(services));

await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r16-overview.png",
});
console.log({ round16Done: true });
