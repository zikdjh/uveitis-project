// Round 07 (B-04): browser-side verification of silent refresh.
//
// The access cookie is deleted to simulate expiry, then the doctor workspace is
// reloaded. The app must refresh once, restore the session and keep the user on
// the workspace instead of bouncing to /login. CDP network events are used to
// count how many refresh calls the app actually made.
const task = await taskSpace("dual token browser verification 20261029");
const page = task.page("p1");

try {
  await page.cdp("Network.enable");
} catch (reason) {
  console.log(JSON.stringify({ networkEnable: String(reason) }));
}

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector("input[name=username]", { timeout: 20000 });
await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]", { label: "登录医生工作台" });
await page.waitForURL("**/doctor/workbench", { timeout: 20000 });

const cookiesBefore = await page.cdp("Network.getAllCookies");
const oldRefresh =
  cookiesBefore.cookies.find((item) => item.name === "uveitis_refresh")?.value ?? "";

await page.events();

await page.cdp("Network.deleteCookies", {
  name: "uveitis_access",
  domain: "127.0.0.1",
  path: "/",
});

await page.goto("http://127.0.0.1:5173/doctor/workbench");
await page.waitForSelector("main", { timeout: 25000 });
await page.waitForTimeout(4000);

const urlAfterReload = await page.url();
const cookiesAfter = await page.cdp("Network.getAllCookies");
const newRefresh =
  cookiesAfter.cookies.find((item) => item.name === "uveitis_refresh")?.value ?? "";
const cookieNames = cookiesAfter.cookies
  .filter((item) => item.name.startsWith("uveitis_"))
  .map((item) => item.name)
  .sort();

const events = await page.events();
const refreshCalls = events.filter((event) => {
  const url = event?.params?.request?.url ?? "";
  return event?.method === "Network.requestWillBeSent" && url.includes("/api/v1/auth/refresh");
}).length;
const meCalls = events.filter((event) => {
  const url = event?.params?.request?.url ?? "";
  return event?.method === "Network.requestWillBeSent" && url.includes("/api/v1/auth/me");
}).length;
const eventMethods = [...new Set(events.map((event) => event?.method))].slice(0, 12);

const bodyText = await page.evaluate(() => {
  const main = document.querySelector("main");
  return (main?.innerText ?? "").replace(/\\n{2,}/g, "\\n").slice(0, 400);
});

console.log(
  JSON.stringify(
    {
      round: "07",
      goal: "B-04 silent refresh in browser",
      urlAfterReload,
      stayedOnWorkspace: urlAfterReload.includes("/doctor/"),
      cookieNames,
      accessRestored: cookieNames.includes("uveitis_access"),
      refreshRotated: Boolean(newRefresh) && oldRefresh !== newRefresh,
      refreshCalls,
      meCalls,
      eventCount: events.length,
      eventMethods,
      bodyText,
    },
    null,
    2,
  ),
);
