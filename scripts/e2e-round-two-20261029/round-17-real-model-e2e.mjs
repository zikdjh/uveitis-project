// Round 17: B-01 real-model end-to-end rerun on the live stack.
//
// Chain under test: doctor login -> create case with an OCT image -> trigger
// auxiliary analysis -> wait for the persistent job to finish -> read back the
// runtime metadata written by the Qwen runtime service (127.0.0.1:8010).
//
// The uploaded fixture is a retained copy of the public OCT image that the
// frozen test set used; it lives under backend/data/uploads and carries no
// patient data. It is a chain fixture only, never a clinical sample.
const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");
const SHOT_DIR = "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029";
const FIXTURE =
  "D:/temp/gpt/uveitis-project/backend/data/uploads/ff09b405-3df1-4df4-bae4-7847c41aa1de/f330c45d-9c59-4cef-a506-7893d0877788.jpg";

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector("h1", { timeout: 20000 });
await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]", { label: "登录医生工作台" });
await page.waitForURL("**/doctor/workbench", { timeout: 20000 });

await page.goto("http://127.0.0.1:5173/doctor/cases/new");
await page.waitForSelector("h1:has-text('新建病例')", { timeout: 20000 });
await page.fill(
  "textarea[placeholder^='例如']",
  "右眼视物模糊伴眼前黑影三天（真实模型端到端复跑）",
);
await page.fill(
  "textarea[placeholder^='既往史']",
  "合成链路测试记录，不含真实患者信息。",
);
await page.selectOption("select >> nth=1", "OD");
await page.selectOption("select >> nth=2", "oct");
await page.setInputFiles("input[type=file]", [FIXTURE]);
await page.click("input[type=checkbox]", { label: "确认病例授权" });
await page.click("button[type=submit]", { label: "创建真实模型验收病例" });
await page.waitForURL("**/summary", { timeout: 60000 });

const caseUrl = await page.url();
const caseId = new URL(caseUrl).pathname.split("/")[3];

await page.goto(`http://127.0.0.1:5173/doctor/cases/${caseId}/analysis`);
await page.waitForSelector("h1, h2", { timeout: 20000 });
await page.click("loc=role:button[name='启动辅助分析']", {
  label: "启动辅助分析",
});

const jobStarted = await page.evaluate(async (cid) => {
  const response = await fetch(`/api/v1/cases/${cid}/analysis-job`, {
    credentials: "include",
  });
  if (!response.ok) return null;
  const data = await response.json();
  return { status: data?.status, attempt: data?.attempt_count };
}, caseId);

await page.waitForFunction(
  async (cid) => {
    const response = await fetch(`/api/v1/cases/${cid}/analysis-job`, {
      credentials: "include",
    });
    if (!response.ok) return false;
    const data = await response.json();
    return Boolean(data) && ["completed", "failed"].includes(data.status);
  },
  caseId,
  { timeout: 240000, polling: 2000 },
);

const detail = await page.evaluate(async (cid) => {
  const response = await fetch(`/api/v1/cases/${cid}`, {
    credentials: "include",
  });
  return response.json();
}, caseId);

const stages = Object.fromEntries(
  (detail.analysis?.stages ?? []).map((item) => [item.key, item.status]),
);
let shot = null;
try {
  shot = await page.screenshot({ path: `${SHOT_DIR}/shot-r17-real-model.png` });
} catch (reason) {
  shot = `screenshot-skipped: ${reason.message}`;
}

const visibleText = await page.evaluate(() => {
  const main = document.querySelector("main");
  return (main?.innerText ?? "").replace(/\n{2,}/g, "\n").slice(0, 1200);
});

console.log(
  JSON.stringify(
    {
      round: 17,
      goal: "B-01 real model end to end",
      spaceId: task.spaceId,
      caseId,
      jobStarted,
      caseStatus: detail.status,
      analysisStatus: detail.analysis?.status,
      modelMode: detail.analysis?.model_mode,
      adapterSha256: detail.analysis?.runtime_metadata?.adapter_sha256,
      modelName: detail.analysis?.runtime_metadata?.model_name,
      peakReservedGib: detail.analysis?.runtime_metadata?.peak_reserved_gib,
      stages,
      visibleText,
      screenshot: shot,
    },
    null,
    2,
  ),
);
