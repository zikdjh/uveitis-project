// Round 18: B-02 failure recovery, degraded half.
//
// The Qwen runtime service on 127.0.0.1:8010 is stopped before this round runs.
// Expected behaviour: only the qwen_judgment stage fails, the persistent job
// still completes, and the case still reaches awaiting_review.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");
const CASE_ID = "47bd1e4c-39c9-48d0-9980-bbbbb4b0e451";

await page.goto(`http://127.0.0.1:5173/doctor/cases/${CASE_ID}/analysis`);
await page.waitForSelector("main", { timeout: 20000 });
await page.click("loc=role:button[name='重新分析']", { label: "重新分析" });

await page.waitForFunction(
  async (cid) => {
    const response = await fetch(`/api/v1/cases/${cid}/analysis-job`, {
      credentials: "include",
    });
    if (!response.ok) return false;
    const data = await response.json();
    return Boolean(data) && ["completed", "failed"].includes(data.status);
  },
  CASE_ID,
  { timeout: 240000, polling: 2000 },
);

const detail = await page.evaluate(async (cid) => {
  const response = await fetch(`/api/v1/cases/${cid}`, {
    credentials: "include",
  });
  const job = await fetch(`/api/v1/cases/${cid}/analysis-job`, {
    credentials: "include",
  });
  const caseData = await response.json();
  const jobData = job.ok ? await job.json() : null;
  return {
    caseStatus: caseData.status,
    analysisStatus: caseData.analysis?.status,
    modelMode: caseData.analysis?.model_mode,
    adapterSha256: caseData.analysis?.runtime_metadata?.adapter_sha256 ?? null,
    stages: (caseData.analysis?.stages ?? []).map((item) => ({
      key: item.key,
      status: item.status,
      detail: item.detail ? String(item.detail).slice(0, 160) : null,
    })),
    jobStatus: jobData?.status,
    attempt: jobData?.attempt_count,
    maxAttempts: jobData?.max_attempts,
  };
}, CASE_ID);

const visibleText = await page.evaluate(() => {
  const main = document.querySelector("main");
  return (main?.innerText ?? "").replace(/\n{2,}/g, "\n").slice(0, 1200);
});

let shot = null;
try {
  shot = await page.screenshot({
    path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r18-degraded.png",
  });
} catch (reason) {
  shot = `screenshot-skipped: ${reason.message}`;
}

console.log(
  JSON.stringify({ round: 18, goal: "B-02 degraded half", ...detail, visibleText, screenshot: shot }, null, 2),
);
