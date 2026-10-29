const task = await taskSpace(3);
const page = task.page("p1");
console.log({
  url: await page.url(),
  title: await page.title(),
});
console.log(await page.snapshot());
