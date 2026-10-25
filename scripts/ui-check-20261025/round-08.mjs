const task = await taskSpace(8);
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/login");
await page.waitForTimeout(500);
console.log(await page.evaluate(() => {
  const root = document.getElementById("root");
  return {
    root: root?.innerHTML,
    scripts: [...document.scripts].map(s => s.src),
    resources: performance.getEntriesByType("resource").map(r => r.name).filter(n => n.includes("/src/")),
  };
}));
