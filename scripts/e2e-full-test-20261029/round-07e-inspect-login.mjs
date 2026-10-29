const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/admin/login");
await page.waitForTimeout(2000);
console.log({ url: await page.url() });

const formInfo = await page.evaluate(() => {
  const inputs = [...document.querySelectorAll("input")];
  return inputs.map((i) => ({
    type: i.type, name: i.name, readOnly: i.readOnly, disabled: i.disabled,
    placeholder: i.placeholder, className: i.className.slice(0, 40),
  }));
});
console.log(formInfo);
