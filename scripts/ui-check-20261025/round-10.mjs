const task = await taskSpace(8);
const page = task.page("p1");
const err = await page.evaluate(() => {
  const log = globalThis.__egoErrors ?? [];
  return { root: document.getElementById("root")?.innerHTML, errors: log };
});
console.log(err);
