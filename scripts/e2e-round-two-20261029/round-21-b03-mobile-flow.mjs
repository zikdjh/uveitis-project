// Round 21 (B-03): 390px continuous doctor flow plus admin console check.
//
// Walks workbench -> case list -> case detail tabs -> review -> report on a
// 390px viewport, saves the review, then checks the admin service page. Every
// step records horizontal overflow, visible controls and console errors.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");
const SHOT_DIR = "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029";
const CASE_ID = "248ef232-c8be-4eee-a7ef-5ef9a4db9148";
const ROUTES = [
  "/doctor/workbench",
  "/doctor/cases",
  `/doctor/cases/${CASE_ID}/summary`,
  `/doctor/cases/${CASE_ID}/images`,
  `/doctor/cases/${CASE_ID}/analysis`,
  `/doctor/cases/${CASE_ID}/review`,
  `/doctor/cases/${CASE_ID}/report`,
  "/doctor/knowledge",
];

try {
  await page.cdp("Runtime.enable");
} catch {}
await page.events();

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector("input[name=username]", { timeout: 20000 });
await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]", { label: "登录医生工作台" });
await page.waitForURL("**/doctor/workbench", { timeout: 20000 });

await page.cdp("Emulation.setDeviceMetricsOverride", {
  width: 390,
  height: 844,
  deviceScaleFactor: 1,
  mobile: true,
});

async function measure(label) {
  const metrics = await page.evaluate(() => {
    const doc = document.documentElement;
    const visible = (node) =>
      node.offsetParent !== null &&
      node.getBoundingClientRect().width > 0 &&
      node.getBoundingClientRect().height > 0;
    const overflow = [...document.querySelectorAll("body *")]
      .filter(visible)
      .filter((node) => node.getBoundingClientRect().right > doc.clientWidth + 1)
      .slice(0, 5)
      .map((node) => ({
        tag: node.tagName.toLowerCase(),
        cls: String(node.className).slice(0, 60),
        right: Math.round(node.getBoundingClientRect().right),
      }));
    return {
      path: location.pathname,
      clientWidth: doc.clientWidth,
      scrollWidth: doc.scrollWidth,
      horizontalOverflow: doc.scrollWidth > doc.clientWidth + 1,
      actionable: [...document.querySelectorAll("button, a[href], input, select, textarea")].filter(visible).length,
      headings: [...document.querySelectorAll("h1, h2")].slice(0, 2).map((n) => n.textContent.trim()),
      overflow,
    };
  });
  return { label, ...metrics };
}

const results = [];
for (const path of ROUTES) {
  await page.goto("http://127.0.0.1:5173" + path);
  await page.waitForSelector("main", { timeout: 20000 });
  await page.waitForTimeout(900);
  results.push(await measure(path));
}

await page.goto(`http://127.0.0.1:5173/doctor/cases/${CASE_ID}/review`);
await page.waitForSelector("form select[name=decision]", { timeout: 20000 });
await page.selectOption("select[name=decision]", { label: "认可结果" });
await page.fill("textarea[name=final_impression]", "左眼葡萄膜炎随访，OCT 未见明显活动性病变，建议 4 周后复诊。");
await page.fill("textarea[name=note]", "B-03 移动端连续流程：医生复核通过。");
await page.click("loc=role:button[name='保存复核']", { label: "保存复核" });
await page.waitForSelector("text=已于", { timeout: 25000 });
const reviewState = await page.evaluate(() => {
  const main = document.querySelector("main");
  return (main?.innerText ?? "").replace(/\\n{2,}/g, "\\n").slice(0, 400);
});

const report = await measure("report-after-review");
await page.goto(`http://127.0.0.1:5173/doctor/cases/${CASE_ID}/report`);
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(900);
const reportText = await page.evaluate(() => {
  const main = document.querySelector("main");
  return (main?.innerText ?? "").replace(/\\n{2,}/g, "\\n").slice(0, 400);
});
const reportShot = await page.screenshot({ path: `${SHOT_DIR}/shot-r21-mobile-report.png` });

await page.goto("http://127.0.0.1:5173/admin/login");
await page.waitForSelector("input[name=password]", { timeout: 20000 });
await page.fill("input[name=password]", "root-20261025");
await page.click("button[type=submit]", { label: "进入管理后台" });
await page.waitForURL("**/admin", { timeout: 20000 });
const adminResults = [];
for (const path of ["/admin", "/admin/services", "/admin/access"]) {
  await page.goto("http://127.0.0.1:5173" + path);
  await page.waitForSelector("main", { timeout: 20000 });
  await page.waitForTimeout(1200);
  adminResults.push(await measure(path));
}
await page.screenshot({ path: `${SHOT_DIR}/shot-r21-mobile-admin-services.png` });

await page.cdp("Emulation.clearDeviceMetricsOverride", {});

const events = await page.events();
const consoleErrors = events
  .filter((event) => event?.method === "Runtime.consoleAPICalled")
  .filter((event) => ["error", "assert"].includes(event?.params?.type))
  .map((event) =>
    (event.params.args ?? [])
      .map((arg) => String(arg.value ?? arg.description ?? ""))
      .join(" ")
      .slice(0, 160),
  );

console.log(
  JSON.stringify(
    {
      round: "21",
      goal: "B-03 mobile 390px continuous flow",
      doctorRoutes: results,
      anyDoctorOverflow: results.some((item) => item.horizontalOverflow),
      adminRoutes: adminResults,
      anyAdminOverflow: adminResults.some((item) => item.horizontalOverflow),
      reviewSaved: reviewState.includes("已于"),
      reviewText: reviewState,
      reportText,
      reportOverflow: report.horizontalOverflow,
      consoleErrors,
      screenshotReport: reportShot,
    },
    null,
    2,
  ),
);
