const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");
const caseId = "ff09b405-3df1-4df4-bae4-7847c41aa1de";

async function runAnalysis() {
  const started = await page.evaluate(async (cid) => {
    const csrf = document.cookie.split(";").map((c) => c.trim())
      .find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "";
    const response = await fetch(`/api/v1/cases/${cid}/analyze`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRF-Token": csrf },
    });
    return response.status;
  }, caseId);

  const result = await page.waitForFunction(async (cid) => {
    const response = await fetch(`/api/v1/cases/${cid}/analysis-job`, { credentials: "include" });
    if (!response.ok) return null;
    const data = await response.json();
    if (data && data.status === "completed") return data;
    return false;
  }, undefined, { timeout: 120000, polling: 2000 });

  const detail = await page.evaluate(async (cid) => {
    const response = await fetch(`/api/v1/cases/${cid}`, { credentials: "include" });
    return response.json();
  }, caseId);

  const qwen = detail.analysis?.stages?.find((s) => s.key === "qwen_judgment");
  return {
    analyzeStatus: started,
    caseStatus: detail.status,
    qwenStatus: qwen?.status,
    qwenDetail: qwen?.detail?.slice(0, 120),
    modelMode: detail.analysis?.model_mode,
  };
}

console.log({ phase: "degraded-run-start" });
const degraded = await runAnalysis();
console.log({ phase: "degraded-run-result", ...degraded });
