const task = await takeOverTaskSpace(2);
const page = task.page("p1");

const urls = [
  "https://www.kaggle.com/datasets/andrewmvd/ocular-disease-recognition-odir5k/data",
  "https://www.kaggle.com/datasets/kondwani/eye-disease-dataset",
  "https://www.kaggle.com/datasets/orvile/eye-diseases-classification",
  "https://www.kaggle.com/datasets/linchundan/fundusimage1000",
  "https://www.kaggle.com/competitions/aptos2019-blindness-detection/data",
];

for (const url of urls) {
  await page.goto(url, { timeout: 60_000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
  const info = await page.evaluate(() => ({
    title: document.title,
    url: location.href,
    bodySnippet: document.body.innerText.slice(0, 1200),
    downloadButtons: [...document.querySelectorAll("button")]
      .filter((node) => /Download/i.test(node.textContent || ""))
      .map((node) => ({
        text: node.textContent?.trim().replace(/\s+/g, " "),
        className: node.className?.toString().slice(0, 80),
      })),
    links: [...document.querySelectorAll("a")].filter((a) =>
      /download|data|files/i.test(a.textContent || "") ||
      /download/.test(a.href || ""),
    ).slice(0, 20).map((a) => ({ text: a.textContent?.trim(), href: a.href })),
  }));
  console.log(JSON.stringify(info));
}
