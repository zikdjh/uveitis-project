const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");

const result = await page.evaluate(async () => {
  const csrf = document.cookie.split(";").map((c) => c.trim())
    .find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "";
  const meResponse = await fetch("/api/v1/auth/me", { credentials: "include" });
  const me = meResponse.ok ? await meResponse.json() : null;
  const searchResponse = await fetch("/api/v1/knowledge/search", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify({ query: "葡萄膜炎 OCT", top_k: 3 }),
  });
  const searchBody = await searchResponse.text();
  return { me: me?.username, mePermissions: me?.permissions, csrfLen: csrf.length, searchStatus: searchResponse.status, searchBody: searchBody.slice(0, 200) };
});
console.log(result);
