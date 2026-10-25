const task = await taskSpace("uveitis figshare downloads 20261024");
const page = task.page("p1");

const ids = [26936446, 19688169, 11371803, 30333775];

for (const id of ids) {
  await page.goto(`https://api.figshare.com/v2/articles/${id}`, { timeout: 45_000 });
  await page.waitForLoadState("load");
  const raw = await page.evaluate(() => document.body.innerText);
  const json = JSON.parse(raw);
  console.log(JSON.stringify({
    id: json.id,
    title: json.title,
    version: json.version,
    license: json.license?.name,
    size: json.size,
    files: (json.files || []).map((file) => ({
      id: file.id,
      name: file.name,
      size: file.size,
      download_url: file.download_url,
    })),
  }, null, 2));
}
