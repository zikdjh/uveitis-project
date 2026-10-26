const task = await taskSpace(1);
const page = task.page("p1");
const endpoints = [
  "https://data.mendeley.com/public-api/datasets/hbr5pwk5w5/versions/1",
  "https://data.mendeley.com/public-api/datasets/hbr5pwk5w5",
  "https://data.mendeley.com/api/datasets/hbr5pwk5w5/versions/1",
  "https://data.mendeley.com/api/datasets/hbr5pwk5w5",
  "https://api.datacite.org/dois/10.17632/hbr5pwk5w5.1",
];
for (const url of endpoints) {
  await page.goto(url, { waitUntil: "domcontentloaded", timeout: 30000 });
  const body = await page.evaluate(() => document.body?.innerText || "");
  console.log(JSON.stringify({ url, title: await page.title(), body: body.slice(0, 12000) }, null, 2));
}

await page.goto("https://data.mendeley.com/datasets/hbr5pwk5w5/1", { waitUntil: "domcontentloaded" });
console.log(JSON.stringify({ snapshot: await page.snapshot() }, null, 2));
