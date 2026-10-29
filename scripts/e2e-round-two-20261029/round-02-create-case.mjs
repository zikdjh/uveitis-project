const task = await taskSpace("uveitis round two e2e 20261029");
const page = task.page("p1");

await page.goto("http://127.0.0.1:5173/doctor/cases");
await page.waitForSelector("main", { timeout: 15000 });

const created = await page.evaluate(async () => {
  const csrf =
    document.cookie
      .split(";")
      .map((item) => item.trim())
      .find((item) => item.startsWith("uveitis_csrf="))
      ?.split("=")
      .slice(1)
      .join("=") ?? "";
  const response = await fetch("/api/v1/cases", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
    body: JSON.stringify({
      patient_age: 34,
      patient_sex: "F",
      complaint: "左眼视物模糊两周，伴轻度眼红",
      medical_history: "否认既往葡萄膜炎病史",
      affected_eye: "OS",
      consent_confirmed: true,
    }),
  });
  return { status: response.status, body: await response.json() };
});

console.log({
  spaceId: task.spaceId,
  createStatus: created.status,
  caseId: created.body?.id,
  caseStatus: created.body?.status,
});

await page.goto(`http://127.0.0.1:5173/doctor/cases/${created.body.id}`);
await page.waitForTimeout(2500);
console.log(await page.snapshot());
