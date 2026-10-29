// Round 08 (B-04): admin sliding session in the browser.
//
// The admin account gets a single short-lived access cookie and no refresh
// cookie. Every successful authenticated request renews the 10 minute window,
// so the cookie expiry must move forward after the admin uses the console.
const task = await taskSpace("dual token browser verification 20261029");
const page = task.page("p1");

async function accessCookie() {
  const cookies = await page.cdp("Network.getAllCookies");
  return cookies.cookies.find((item) => item.name === "uveitis_access") ?? null;
}

await page.goto("http://127.0.0.1:5173/admin/login");
await page.waitForSelector("input[name=password]", { timeout: 20000 });
await page.fill("input[name=password]", "root-20261025");
await page.click("button[type=submit]", { label: "进入管理后台" });
await page.waitForURL("**/admin", { timeout: 20000 });
await page.waitForTimeout(1500);

const cookieNames = (await page.cdp("Network.getAllCookies")).cookies
  .filter((item) => item.name.startsWith("uveitis_"))
  .map((item) => item.name)
  .sort();
const first = await accessCookie();
const firstExpiry = first?.expires ?? null;
const ttlFirst = firstExpiry ? Math.round(firstExpiry - Date.now() / 1000) : null;

// Stay idle, then use the console so the sliding window renews.
await page.waitForTimeout(4000);
await page.goto("http://127.0.0.1:5173/admin/services");
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(2500);

const second = await accessCookie();
const secondExpiry = second?.expires ?? null;
const ttlSecond = secondExpiry ? Math.round(secondExpiry - Date.now() / 1000) : null;

const url = await page.url();
console.log(
  JSON.stringify(
    {
      round: "08",
      goal: "B-04 admin sliding session",
      url,
      cookieNames,
      hasRefreshCookie: cookieNames.includes("uveitis_refresh"),
      ttlFirstSeconds: ttlFirst,
      ttlSecondSeconds: ttlSecond,
      expiryMovedForward:
        firstExpiry !== null && secondExpiry !== null && secondExpiry > firstExpiry,
      stillWithinTenMinutes:
        ttlSecond !== null && ttlSecond > 0 && ttlSecond <= 600,
      stayedOnAdmin: url.includes("/admin"),
    },
    null,
    2,
  ),
);
