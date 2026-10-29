const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");

const detail = await page.evaluate(async () => {
  const [jobRes, caseRes] = await Promise.all([
    fetch("/api/v1/cases/ff09b405-3df1-4df4-bae4-7847c41aa1de/analysis-job", { credentials: "include" }),
    fetch("/api/v1/cases/ff09b405-3df1-4df4-bae4-7847c41aa1de", { credentials: "include" }),
  ]);
  const job = await jobRes.json();
  const caseData = await caseRes.json();
  const qwen = caseData.analysis?.stages?.find((s) => s.key === "qwen_judgment");
  return {
    jobStatus: job?.status,
    attemptCount: job?.attempt_count,
    maxAttempts: job?.max_attempts,
    jobError: job?.error?.slice(0, 120),
    caseStatus: caseData.status,
    qwenStatus: qwen?.status,
    qwenDetail: qwen?.detail?.slice(0, 120),
    modelMode: caseData.analysis?.model_mode,
  };
});
console.log(detail);
