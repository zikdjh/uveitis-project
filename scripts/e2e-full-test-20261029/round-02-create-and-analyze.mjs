const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/doctor/cases");
await page.waitForTimeout(1500);

await page.evaluate(() => {
  const buttons = [...document.querySelectorAll("button")];
  const btn = buttons.find((b) => b.textContent.includes("新建病例"));
  if (btn) btn.click();
});
await page.waitForTimeout(1500);

const formText = await page.evaluate(() => document.body.innerText.slice(0, 800));
console.log({ formText });
