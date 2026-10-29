const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");

const detail = await page.evaluate(async () => {
  const response = await fetch("/api/v1/cases/ff09b405-3df1-4df4-bae4-7847c41aa1de", { credentials: "include" });
  return response.json();
});

const qwenStage = detail.analysis?.stages?.find((s) => s.key === "qwen_judgment");
console.log({
  qwenStage,
  modelMode: detail.analysis?.model_mode,
  adapterSha: detail.analysis?.runtime_metadata?.adapter_sha256?.slice(0, 12),
  analysisDetail: detail.analysis?.detail?.slice(0, 300),
});
