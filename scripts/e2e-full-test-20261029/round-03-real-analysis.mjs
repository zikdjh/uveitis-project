const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");
const caseId = "ff09b405-3df1-4df4-bae4-7847c41aa1de";

await page.goto(`http://127.0.0.1:5173/doctor/cases/${caseId}/analysis`);
await page.waitForTimeout(2000);

const beforeApi = await page.evaluate(async () => {
  const response = await fetch("/api/v1/cases/ff09b405-3df1-4df4-bae4-7847c41aa1de", { credentials: "include" });
  return response.json();
});
console.log({ phase: "before", status: beforeApi.status, modelMode: beforeApi.analysis?.model_mode });

const started = await page.evaluate(async () => {
  const csrf = document.cookie.split(";").map((c) => c.trim())
    .find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "";
  const response = await fetch("/api/v1/cases/ff09b405-3df1-4df4-bae4-7847c41aa1de/analyze", {
    method: "POST",
    credentials: "include",
    headers: { "X-CSRF-Token": csrf },
  });
  return { status: response.status };
});
console.log({ phase: "analyze-started", ...started });

const job = await page.waitForFunction(async () => {
  const response = await fetch("/api/v1/cases/ff09b405-3df1-4df4-bae4-7847c41aa1de/analysis-job", { credentials: "include" });
  if (!response.ok) return null;
  const data = await response.json();
  if (data && data.status === "completed") return data;
  return false;
}, undefined, { timeout: 120000, polling: 2000 });

const afterApi = await page.evaluate(async () => {
  const [caseResponse, jobResponse] = await Promise.all([
    fetch("/api/v1/cases/ff09b405-3df1-4df4-bae4-7847c41aa1de", { credentials: "include" }),
    fetch("/api/v1/cases/ff09b405-3df1-4df4-bae4-7847c41aa1de/analysis-job", { credentials: "include" }),
  ]);
  const caseData = await caseResponse.json();
  const jobData = await jobResponse.json();
  return {
    caseStatus: caseData.status,
    modelMode: caseData.analysis?.model_mode,
    adapterSha: caseData.analysis?.runtime_metadata?.adapter_sha256?.slice(0, 12),
    stages: caseData.analysis?.stages?.map((s) => ({ key: s.key, status: s.status })),
    jobStatus: jobData.status,
    attemptCount: jobData.attempt_count,
  };
});

console.log({ phase: "after", ...afterApi });
