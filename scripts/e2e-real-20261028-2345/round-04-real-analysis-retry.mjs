const task = await taskSpace(3);
const page = task.page("p1");
const caseId = "ff09b405-3df1-4df4-bae4-7847c41aa1de";

await page.goto(`http://127.0.0.1:5173/doctor/cases/${caseId}/analysis`);
await page.waitForSelector(".section-heading h2:has-text('辅助分析')");
await page.click("button.primary", { label: "启动真实模型辅助分析" });

const jobResponse = await page.fetch(
  `/api/v1/cases/${caseId}/analysis-job`,
);
const job = JSON.parse(jobResponse.body);
console.log({
  phase: "started",
  jobStatus: job?.status,
  attemptCount: job?.attempt_count,
  maxAttempts: job?.max_attempts,
});

await page.waitForFunction(
  () => {
    const statuses = [...document.querySelectorAll(".analysis-summary strong")];
    return statuses.some((node) => node.textContent?.trim() === "分析完成");
  },
  undefined,
  { timeout: 120000 },
);

const screenshot = await page.screenshot({
  path: "D:/temp/gpt/uveitis-project/scripts/e2e-real-20261028-2345/analysis-completed-desktop.png",
});
console.log({
  phase: "completed",
  url: await page.url(),
  screenshot,
});
console.log(await page.snapshot());
