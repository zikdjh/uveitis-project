const task = await taskSpace(1);
const page = task.page("p1");
const targets = [
  "https://anjos.ai/projects/uveitis/",
  "https://archive.ics.uci.edu/dataset/430/oct+data+color+fundus+images+of+left+right+eyes",
  "https://data.mendeley.com/datasets/hbr5pwk5w5/1",
];
for (const target of targets) {
  await page.goto(target, { waitUntil: "domcontentloaded", timeout: 30000 });
  await page.waitForTimeout(1000);
  const data = await page.evaluate(() => ({
    title: document.title,
    url: location.href,
    body: document.body?.innerText?.replace(/\s+/g, " ").slice(0, 14000),
    links: [...document.querySelectorAll("a")].map((a) => ({ text: a.innerText?.trim(), href: a.href }))
      .filter((a) => /download|data|github|license|dataset|zenodo|figshare|doi/i.test(`${a.text} ${a.href}`))
      .slice(0, 120),
  }));
  console.log(JSON.stringify({ target, ...data }, null, 2));
}

await page.goto("https://data.mendeley.com/public-api/datasets/hbr5pwk5w5/files?folder_id=root&version=1", { waitUntil: "domcontentloaded" });
console.log(JSON.stringify({ mendeleyFileApi: await page.evaluate(() => document.body?.innerText || "") }, null, 2));
