const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector("form", { timeout: 10000 });
await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]");
await page.waitForURL("**/doctor/workbench", { timeout: 15000 });

await page.goto("http://127.0.0.1:5173/doctor/cases");
await page.waitForTimeout(1500);

const added = await page.evaluate(async () => {
  const csrf = document.cookie.split(";").map((c) => c.trim())
    .find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "";
  const response = await fetch("/api/v1/knowledge/documents", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify({
      title: "前葡萄膜炎活动性 OCT 特征",
      content: "前葡萄膜炎活动期 OCT 常见前房细胞、房水闪辉、虹膜后粘连；OCT 可见黄斑水肿、视网膜下渗出。鉴别诊断需结合临床查体，单纯 OCT 不能确诊。",
      category: "guideline",
    }),
  });
  return { status: response.status, body: await response.json() };
});

const searched = await page.evaluate(async () => {
  const csrf = document.cookie.split(";").map((c) => c.trim())
    .find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "";
  const response = await fetch("/api/v1/knowledge/search", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify({ query: "前葡萄膜炎 OCT 黄斑水肿", top_k: 3 }),
  });
  return { status: response.status, body: await response.json() };
});

console.log({
  addStatus: added.status,
  addTitle: added.body?.title,
  searchStatus: searched.status,
  hitCount: searched.body?.length,
  topHitTitle: searched.body?.[0]?.title,
  topHitScore: searched.body?.[0]?.score,
});
