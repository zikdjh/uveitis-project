const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://www.kaggle.com/settings/api", { timeout: 60_000 });
await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
console.log({ url: await page.url(), title: await page.title() });
console.log(await page.evaluate(() => ({
  text: document.body.innerText.slice(0, 4000),
  buttons: [...document.querySelectorAll("button")].map((b) => b.innerText?.trim()).filter(Boolean).slice(0, 40),
})));
