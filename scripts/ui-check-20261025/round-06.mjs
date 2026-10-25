const task = await taskSpace(8);
const page = task.page("p1");
const errors = await page.evaluate(() => ({
  url: location.href,
  root: document.getElementById("root")?.innerHTML,
  title: document.title,
}));
console.log(errors);
console.log(await page.snapshot());
