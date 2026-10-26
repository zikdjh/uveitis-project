const task = await taskSpace(1);
const page = task.page("p1");
const targets = [
  "https://www.nature.com/articles/s41597-026-07494-8",
  "https://research-information.bris.ac.uk/en/datasets/3d-oct-images-of-murine-uveitis/",
  "https://data.mendeley.com/datasets/hbr5pwk5w5/1",
];

for (const target of targets) {
  try {
    await page.goto(target, { waitUntil: "domcontentloaded", timeout: 30000 });
    await page.waitForTimeout(1000);
    const info = await page.evaluate(() => ({
      title: document.title,
      url: location.href,
      meta: [...document.querySelectorAll("meta")].map((m) => ({
        name: m.getAttribute("name") || m.getAttribute("property"),
        content: m.getAttribute("content"),
      })).filter((m) => m.name && /description|license|access|citation/i.test(m.name)),
      body: document.body?.innerText?.replace(/\s+/g, " ").slice(0, 12000),
      links: [...document.querySelectorAll("a")].map((a) => ({ text: a.innerText?.trim(), href: a.href }))
        .filter((a) => /download|figshare|zenodo|data|license|supplement|github/i.test(`${a.text} ${a.href}`))
        .slice(0, 80),
    }));
    console.log(JSON.stringify(info, null, 2));
  } catch (error) {
    console.log(JSON.stringify({ target, error: String(error) }));
  }
}
