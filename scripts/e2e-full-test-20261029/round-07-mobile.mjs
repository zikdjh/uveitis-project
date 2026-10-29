const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");
const caseId = "ff09b405-3df1-4df4-bae4-7847c41aa1de";

await page.cdp("Emulation.setDeviceMetricsOverride", {
  width: 390, height: 844, deviceScaleFactor: 2, mobile: true,
});

const pages = [
  { name: "workbench", url: "http://127.0.0.1:5173/doctor/workbench" },
  { name: "cases", url: "http://127.0.0.1:5173/doctor/cases" },
  { name: "case-detail", url: `http://127.0.0.1:5173/doctor/cases/${caseId}` },
  { name: "case-analysis", url: `http://127.0.0.1:5173/doctor/cases/${caseId}/analysis` },
  { name: "case-review", url: `http://127.0.0.1:5173/doctor/cases/${caseId}/review` },
  { name: "case-report", url: `http://127.0.0.1:5173/doctor/cases/${caseId}/report` },
  { name: "knowledge", url: "http://127.0.0.1:5173/doctor/knowledge" },
  { name: "security", url: "http://127.0.0.1:5173/doctor/security" },
];

const results = [];
for (const target of pages) {
  await page.goto(target.url);
  await page.waitForTimeout(1200);
  const check = await page.evaluate(() => {
    const overflow = document.documentElement.scrollWidth > window.innerWidth + 2;
    const buttons = [...document.querySelectorAll("button")];
    const visible = buttons.filter((b) => {
      const rect = b.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    });
    const texts = [...document.querySelectorAll("*")].filter((el) => {
      const rect = el.getBoundingClientRect();
      return rect.right > window.innerWidth + 5 && rect.width < window.innerWidth;
    }).length;
    return {
      overflow,
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      buttonCount: visible.length,
      overflowTextCount: texts,
      title: document.title.slice(0, 30),
    };
  });
  results.push({ page: target.name, ...check });
}

console.log(results);
await page.cdp("Emulation.clearDeviceMetricsOverride");
