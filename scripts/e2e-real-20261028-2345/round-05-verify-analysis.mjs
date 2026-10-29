const task = await taskSpace(3);
const page = task.page("p1");
const caseId = "ff09b405-3df1-4df4-bae4-7847c41aa1de";

const caseResponse = await page.fetch(`/api/v1/cases/${caseId}`);
const jobResponse = await page.fetch(
  `/api/v1/cases/${caseId}/analysis-job`,
);
const caseData = JSON.parse(caseResponse.body);
const job = JSON.parse(jobResponse.body);
console.log({
  caseStatus: caseData.status,
  analysisStatus: caseData.analysis?.status,
  modelMode: caseData.analysis?.model_mode,
  adapterSha256: caseData.analysis?.runtime_metadata?.adapter_sha256,
  jobStatus: job?.status,
  attemptCount: job?.attempt_count,
  maxAttempts: job?.max_attempts,
  error: job?.error,
});
console.log(await page.snapshot());
