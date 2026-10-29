const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/doctor/cases");
await page.waitForTimeout(1500);

await page.evaluate(() => {
  const btn = [...document.querySelectorAll("button, a")].find(
    (el) => el.textContent.includes("新建病例"),
  );
  if (btn) btn.click();
});
await page.waitForTimeout(2000);

console.log({ url: await page.url() });
const hasForm = await page.evaluate(() => {
  const inputs = [...document.querySelectorAll("input, select, textarea")];
  return inputs.map((i) => ({ tag: i.tagName, type: i.type, name: i.name, placeholder: i.placeholder }));
});
console.log({ hasForm });
