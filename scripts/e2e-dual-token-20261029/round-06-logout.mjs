const task = await taskSpace("dual token browser verification 20261029");
const page = task.page("p1");

const before = await page.cdp("Network.getAllCookies");
const beforeAuth = before.cookies.filter((c) => c.name.startsWith("uveitis_")).map((c) => c.name);

await page.evaluate(async () => {
  const m = document.cookie.match(/uveitis_csrf=([^;]+)/);
  const csrf = m ? decodeURIComponent(m[1]) : "";
  await fetch("/api/v1/auth/logout", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrf },
  });
});

const after = await page.cdp("Network.getAllCookies");
const afterAuth = after.cookies.filter((c) => c.name.startsWith("uveitis_")).map((c) => c.name);

const meAfterLogout = await page.evaluate(async () => {
  const response = await fetch("/api/v1/auth/me", { credentials: "include" });
  return response.status;
});

console.log({
  cookiesBeforeLogout: beforeAuth,
  cookiesAfterLogout: afterAuth,
  allCleared: afterAuth.length === 0,
  meStatusAfterLogout: meAfterLogout,
});
