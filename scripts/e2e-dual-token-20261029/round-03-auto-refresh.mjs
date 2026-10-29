const task = await taskSpace("dual token browser verification 20261029");
const page = task.page("p1");

const before = await page.evaluate(async () => {
  const cookies = document.cookie.split(";").map((c) => c.trim().split("=")[0]);
  return { accessibleCookies: cookies };
});

const oldRefresh = await page.cdp("Network.getAllCookies");
const oldRefreshToken = oldRefresh.cookies.find((c) => c.name === "uveitis_refresh")?.value ?? "";

await page.cdp("Network.deleteCookies", {
  name: "uveitis_access",
  domain: "127.0.0.1",
  path: "/",
});

const result = await page.evaluate(async () => {
  try {
    const response = await fetch("/api/v1/auth/me", { credentials: "include" });
    if (response.status === 401) {
      const refreshResponse = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": document.cookie.split(";").map((c) => c.trim()).find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "",
        },
      });
      if (refreshResponse.ok) {
        const retry = await fetch("/api/v1/auth/me", { credentials: "include" });
        return { firstStatus: 401, refreshStatus: refreshResponse.status, retryStatus: retry.status, user: await retry.json() };
      }
      return { firstStatus: 401, refreshStatus: refreshResponse.status, retryStatus: -1 };
    }
    return { firstStatus: response.status, refreshStatus: -1, retryStatus: -1 };
  } catch (error) {
    return { error: String(error) };
  }
});

const afterCookies = await page.cdp("Network.getAllCookies");
const newRefreshToken = afterCookies.cookies.find((c) => c.name === "uveitis_refresh")?.value ?? "";

console.log({
  before,
  result,
  refreshRotated: oldRefreshToken !== newRefreshToken,
  newRefreshSet: Boolean(newRefreshToken),
});
