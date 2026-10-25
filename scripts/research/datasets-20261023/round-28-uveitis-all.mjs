const task = await taskSpace("uveitis figshare downloads 20261024");
const page = task.page("p1");

await page.goto("https://figshare.com/articles/dataset/Uveitis_All_2025_Oct/30333775", { timeout: 45_000 });
await page.waitForTimeout(10_000);

const detail = await page.evaluate(() => {
  const targets = [...document.querySelectorAll("a, button")].map((node) => ({
    tag: node.tagName.toLowerCase(),
    text: node.textContent?.trim() || "",
    href: node instanceof HTMLAnchorElement ? node.href : null,
  })).filter((x) => /download/i.test(x.text) || /ndownloader/i.test(x.href || ""));
  return { title: document.title, bodyStart: document.body.innerText.slice(0, 500), targets: targets.slice(0, 30) };
});

console.log({ url: await page.url(), title: await page.title() });
console.log(JSON.stringify(detail, null, 2));
