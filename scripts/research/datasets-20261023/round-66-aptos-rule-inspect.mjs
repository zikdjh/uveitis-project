const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://www.kaggle.com/competitions/aptos2019-blindness-detection/rules", { timeout: 60_000 });
await page.waitForLoadState("load", { timeout: 30_000 }).catch(() => {});
const data = await page.evaluate(() => ({
  buttons: [...document.querySelectorAll("button")].map((b) => ({
    text: b.innerText?.trim().replace(/\s+/g, " "),
    aria: b.getAttribute("aria-label"),
  })),
  links: [...document.querySelectorAll("a")].filter((a) =>
    /data|accept|rules/i.test(a.innerText || a.href || ""),
  ).map((a) => ({ text: a.innerText?.trim(), href: a.href })).slice(0, 30),
  textTail: document.body.innerText.slice(-2500),
}));
console.log(JSON.stringify(data, null, 2));
