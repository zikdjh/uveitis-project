const task = await taskSpace("dual token browser verification 20261029");
const page = task.page("p1");

async function getRefreshCookie() {
  const all = await page.cdp("Network.getAllCookies");
  return all.cookies.find((c) => c.name === "uveitis_refresh") ?? null;
}

const original = await getRefreshCookie();
if (!original) { console.log({ error: "no refresh cookie" }); process.exit(1); }

const refreshOnce = () => page.evaluate(async () => {
  const m = document.cookie.match(/uveitis_csrf=([^;]+)/);
  const csrf = m ? decodeURIComponent(m[1]) : "";
  const response = await fetch("/api/v1/auth/refresh", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrf },
  });
  return { status: response.status, ok: response.ok };
});

const first = await refreshOnce();
const afterFirst = await getRefreshCookie();

await page.cdp("Network.setCookie", {
  name: "uveitis_refresh",
  value: original.value,
  domain: original.domain,
  path: original.path,
  httpOnly: true,
  secure: false,
  sameSite: "Lax",
});

const second = await refreshOnce();
const afterSecond = await getRefreshCookie();

console.log({
  first,
  second,
  tokenAfterFirst: afterFirst?.value?.slice(0, 12),
  tokenAfterSecond: afterSecond?.value?.slice(0, 12),
  replayReturnsFirstToken: afterFirst?.value === afterSecond?.value,
  originalTokenRotated: original?.value !== afterFirst?.value,
});
