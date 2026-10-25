const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://physionet.org/content/brazilian-ophthalmological/", { timeout: 60_000 });
await page.waitForLoadState("load", { timeout: 30_000 }).catch(() => {});
console.log({ url: await page.url(), title: await page.title() });
console.log(JSON.stringify(await page.evaluate(() => ({
  text: document.body.innerText.slice(0, 5000),
  links: [...document.querySelectorAll("a")].map((a) => ({
    text: a.innerText?.trim(),
    href: a.href,
  })).filter((x) => /log ?in|sign ?in|register|download|data|files|credential|dua|license/i.test(x.text || x.href)).slice(0, 60),
})), null, 2));
