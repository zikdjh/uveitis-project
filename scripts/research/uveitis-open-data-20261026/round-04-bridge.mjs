const task = await taskSpace(1);
const page = task.page("p1");

const urls = [
  "https://zenodo.org/api/records?q=uveitis%20OCT&size=100",
  "https://zenodo.org/api/records?q=uveitis%20optical%20coherence%20tomography&size=100",
  "https://zenodo.org/api/records?q=birdshot&size=100",
];

for (const url of urls) {
  await page.goto(url, { waitUntil: "domcontentloaded" });
  const text = await page.evaluate(() => document.body?.innerText || "");
  try {
    const data = JSON.parse(text);
    console.log(JSON.stringify({
      url,
      total: data.hits?.total,
      items: (data.hits?.hits || []).map((item) => ({
        id: item.id,
        doi: item.doi,
        title: item.metadata?.title,
        access: item.metadata?.access_right,
        license: item.metadata?.license,
        publication_date: item.metadata?.publication_date,
        resource_type: item.metadata?.resource_type,
        files: item.files?.map((f) => ({ key: f.key, size: f.size, checksum: f.checksum })),
        links: item.links,
      })),
    }, null, 2));
  } catch (error) {
    console.log(JSON.stringify({ url, title: await page.title(), body: text.slice(0, 3000), error: String(error) }));
  }
}
