// Round 11: analysis stage page and report content.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");
const CASE_ID = "d8dbb123-20de-4001-8156-e4daa28816b4";

await page.goto(`http://127.0.0.1:5173/doctor/cases/${CASE_ID}/analysis`);
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1500);

const analysis = await page.evaluate(() => {
  const main = document.querySelector("main");
  return {
    path: location.pathname,
    stepItems: [...document.querySelectorAll(".ant-steps-item")].map((n) => n.textContent.trim()),
    text: (main?.innerText ?? "").replace(/\n{2,}/g, "\n").slice(0, 1200),
  };
});
console.log("ANALYSIS " + JSON.stringify(analysis));
await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r11-analysis.png",
});

await page.goto(`http://127.0.0.1:5173/doctor/cases/${CASE_ID}/report`);
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1000);
const report = await page.evaluate(() => {
  const main = document.querySelector("main");
  return { path: location.pathname, text: (main?.innerText ?? "").replace(/\n{2,}/g, "\n").slice(0, 1200) };
});
console.log("REPORT " + JSON.stringify(report));

console.log({ round11Done: true });
