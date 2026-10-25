const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://physionet.org/content/brazilian-ophthalmological/1.0.2/", {
  timeout: 60_000,
  waitUntil: "domcontentloaded",
}).catch((e) => console.log({ gotoWarning: e.message }));
await page.waitForTimeout(5_000);
console.log(JSON.stringify({
  url: await page.url(),
  title: await page.title(),
  text: (await page.evaluate(() => document.body.innerText)).slice(0, 6000),
  links: await page.evaluate(() =>
    [...document.querySelectorAll("a")].map((a) => ({
      text: a.innerText?.trim(),
      href: a.href,
    })).filter((x) => /login|credential|download|files|license|agreement|dua|request|register/i.test(x.text || x.href)).slice(0, 60),
  ),
}, null, 2));
