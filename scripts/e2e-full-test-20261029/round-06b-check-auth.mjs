const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/login");
await page.waitForTimeout(1000);

const me = await page.evaluate(async () => {
  const response = await fetch("/api/v1/auth/me", { credentials: "include" });
  return { status: response.status, body: await response.json() };
});
console.log(me);
