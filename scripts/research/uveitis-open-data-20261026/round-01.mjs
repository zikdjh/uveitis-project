const task = await taskSpace("uveitis-open-data-20261026");
const page = task.page("p1");

const queries = [
  "uveitis OCT dataset open access downloadable",
  "uveitis optical coherence tomography public dataset figshare",
  "infectious uveitis imaging dataset open access",
  "tuberculosis uveitis OCT dataset",
];

for (const query of queries) {
  const url = `https://www.google.com/search?q=${encodeURIComponent(query)}`;
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  const results = await page.evaluate(() =>
    [...document.querySelectorAll("a")]
      .map((a) => ({ text: a.innerText?.trim(), href: a.href }))
      .filter((item) => item.href?.startsWith("http") && item.text?.length > 20)
      .slice(0, 12)
  );
  console.log(JSON.stringify({ query, url: await page.url(), title: await page.title(), results }, null, 2));
}

console.log({ spaceId: task.spaceId, page: page.label });
