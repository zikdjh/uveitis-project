const task = await taskSpace("full round one test 20261029");
const page = task.page("p1");
const caseId = "ff09b405-3df1-4df4-bae4-7847c41aa1de";

const reviewed = await page.evaluate(async (cid) => {
  const csrf = document.cookie.split(";").map((c) => c.trim())
    .find((c) => c.startsWith("uveitis_csrf="))?.split("=").slice(1).join("=") ?? "";
  const response = await fetch(`/api/v1/cases/${cid}/review`, {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify({
      decision: "accepted",
      final_impression: "左眼 OCT 未见明显活动性病变，建议随访。",
      note: "全量测试第一轮：医生复核通过。",
      reviewer: "示例医生",
    }),
  });
  return { status: response.status, body: await response.json() };
}, caseId);

const refreshed = await page.evaluate(async (cid) => {
  const response = await fetch(`/api/v1/cases/${cid}`, { credentials: "include" });
  return response.json();
}, caseId);

console.log({
  reviewStatus: reviewed.status,
  caseStatusAfter: refreshed.status,
  finalImpression: refreshed.review?.final_impression?.slice(0, 40),
  reviewer: refreshed.review?.reviewer,
});
