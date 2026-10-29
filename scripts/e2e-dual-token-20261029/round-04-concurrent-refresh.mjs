const task = await taskSpace("dual token browser verification 20261029");
const page = task.page("p1");

const beforeCookies = await page.cdp("Network.getAllCookies");
const oldRefresh = beforeCookies.cookies.find((c) => c.name === "uveitis_refresh")?.value ?? "";

await page.cdp("Network.deleteCookies", {
  name: "uveitis_access",
  domain: "127.0.0.1",
  path: "/",
});

const result = await page.evaluate(async () => {
  const csrfToken = document.cookie.split(";").map((c) => c.trim())
    .find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "";

  const refreshCalls = [];
  const promises = [1, 2, 3].map((n) => (async () => {
    const first = await fetch("/api/v1/auth/me", { credentials: "include" });
    if (first.status !== 401) return { request: n, firstStatus: first.status };

    const refreshPromise = fetch("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": csrfToken },
    });
    refreshCalls.push(refreshPromise);
    const refreshResponse = await refreshPromise;
    if (!refreshResponse.ok) return { request: n, firstStatus: 401, refreshStatus: refreshResponse.status };

    const retry = await fetch("/api/v1/auth/me", { credentials: "include" });
    return { request: n, firstStatus: 401, refreshStatus: refreshResponse.status, retryStatus: retry.status };
  })());

  const outcomes = await Promise.all(promises);
  return { outcomes, refreshCallCount: refreshCalls.length };
});

const afterCookies = await page.cdp("Network.getAllCookies");
const newRefresh = afterCookies.cookies.find((c) => c.name === "uveitis_refresh")?.value ?? "";

const allSucceeded = result.outcomes.every(
  (o) => o.firstStatus === 401 && o.refreshStatus === 200 && o.retryStatus === 200,
);

console.log({
  ...result,
  allSucceeded,
  oldRefreshCaptured: Boolean(oldRefresh),
  refreshRotated: oldRefresh !== newRefresh,
  newRefreshSet: Boolean(newRefresh),
});
