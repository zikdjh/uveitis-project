const task = await taskSpace(1);
const page = task.page("p1");
const query = "uveitis OCT dataset CC BY 4.0";
await page.goto(`https://www.google.com/search?q=${encodeURIComponent(query)}`, { waitUntil: "domcontentloaded" });
await page.waitForTimeout(1000);
const results = await page.evaluate(() =>
  [...document.querySelectorAll("a")]
    .map((a) => ({ text: a.innerText?.trim(), href: a.href }))
    .filter((item) => item.href?.startsWith("http") && item.text?.length > 20)
    .slice(0, 30)
);
console.log(JSON.stringify({ query, results }, null, 2));

const zenodoSearch = [
  "https://zenodo.org/search?q=uveitis%20OCT",
  "https://zenodo.org/search?q=uveitis%20optical%20coherence%20tomography",
];
for (const url of zenodoSearch) {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  const items = await page.evaluate(() => ({
    title: document.title,
    body: document.body?.innerText?.replace(/\s+/g, " ").slice(0, 14000),
    links: [...document.querySelectorAll("a[href*='/records/']")].map((a) => ({ text: a.innerText?.trim(), href: a.href })).slice(0, 100),
  }));
  console.log(JSON.stringify({ url, ...items }, null, 2));
}
