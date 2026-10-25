const task = await taskSpace(8);
const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/login");
const cookie = await page.evaluate(async () => {
  const response = await fetch("/api/v1/auth/login", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ username: "doctor", password: "doctor-dev-2026" }),
  });
  const me = await fetch("/api/v1/auth/me");
  const cases = await fetch("/api/v1/cases");
  return { login: response.status, me: me.status, cases: cases.status, body: await me.text(), documentCookie: document.cookie };
});
console.log(cookie);
await page.goto("http://127.0.0.1:5173/doctor/workbench");
await page.waitForTimeout(1000);
console.log(await page.evaluate(async () => ({
  url: location.href,
  root: document.getElementById("root")?.innerHTML,
  me: await fetch("/api/v1/auth/me").then(r => r.status),
  caseStatus: await fetch("/api/v1/cases").then(r => r.status),
})));
