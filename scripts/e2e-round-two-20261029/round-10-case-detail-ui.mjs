// Round 10: case detail, review and report pages at desktop viewport.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");
const CASE_ID = "d8dbb123-20de-4001-8156-e4daa28816b4";

await page.cdp("Emulation.clearDeviceMetricsOverride", {});

await page.goto(`http://127.0.0.1:5173/doctor/cases/${CASE_ID}/summary`);
await page.waitForSelector("main", { timeout: 20000 });
await page.waitForTimeout(1200);

const caseNav = await page.evaluate(() => ({
  path: location.pathname,
  heading: document.querySelector("h1")?.textContent?.trim() ?? null,
  links: [...document.querySelectorAll('a[href^="/doctor/cases/"]')].map((a) => a.getAttribute("href")),
  stageTexts: [...document.querySelectorAll("li, .ant-timeline-item, [class*=stage]")]
    .map((n) => n.textContent.trim())
    .filter((t) => t && t.length < 60)
    .slice(0, 20),
}));
console.log("SUMMARY " + JSON.stringify(caseNav));

await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r10-case-summary.png",
});

for (const suffix of ["review", "report"]) {
  await page.goto(`http://127.0.0.1:5173/doctor/cases/${CASE_ID}/${suffix}`);
  await page.waitForSelector("main", { timeout: 20000 });
  await page.waitForTimeout(1000);
  const facts = await page.evaluate(() => ({
    path: location.pathname,
    heading: document.querySelector("h1")?.textContent?.trim() ?? null,
    subHeadings: [...document.querySelectorAll("h2, h3")].map((n) => n.textContent.trim()).slice(0, 10),
    actionable: [...document.querySelectorAll("button, a[href]")].filter((n) => n.offsetParent !== null).length,
  }));
  console.log("PAGE " + JSON.stringify(facts));
  await page.screenshot({
    path: `D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r10-case-${suffix}.png`,
  });
}

console.log({ detailDone: true });
