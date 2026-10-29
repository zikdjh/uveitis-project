const task = await taskSpace("uveitis-real-model-e2e-20261028-2345");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/login");
await page.waitForSelector("h1:has-text('医生登录')");
await page.fill("input[name=username]", "doctor");
await page.fill("input[name=password]", "doctor-dev-2026");
await page.click("button[type=submit]", { label: "登录医生工作台" });
await page.waitForURL("**/doctor/workbench", { timeout: 15000 });

await page.goto("http://127.0.0.1:5173/doctor/cases/new");
await page.waitForSelector("h1:has-text('新建病例')");
await page.fill(
  "textarea[placeholder^='例如']",
  "Codex 真实模型端到端验收：右眼视物模糊伴黑影三天",
);
await page.fill(
  "textarea[placeholder^='既往史']",
  "合成测试记录，不含真实患者信息。",
);
await page.selectOption("select >> nth=1", "OD");
await page.setInputFiles("input[type=file]", [
  "D:/temp/gpt/uveitis-project/model-training/datasets/training/data/01_uveitis_oct/01_uveitis_oct/Optical Coherence Tomography (OCT) Images of Proliferative Vitreoretinopathy, Uveitis, and Normal Eyes/Intermediate+Posterior Uveitis/Int+Post Uveitis 1.jpeg",
]);
await page.click("input[type=checkbox]", { label: "确认合成测试数据授权" });
await page.click("button[type=submit]", { label: "创建真实模型验收病例" });
await page.waitForURL("**/summary", { timeout: 30000 });
await page.waitForSelector(".case-tabs");

console.log({
  spaceId: task.spaceId,
  url: await page.url(),
});
console.log(await page.snapshot());
