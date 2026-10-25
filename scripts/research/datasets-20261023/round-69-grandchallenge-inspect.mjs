const task = await takeOverTaskSpace(2);
const page = task.page("p1");

for (const url of [
  "https://idrid.grand-challenge.org/",
  "https://drive.grand-challenge.org/",
]) {
  await page.goto(url, { timeout: 60_000 });
  await page.waitForLoadState("load", { timeout: 30_000 }).catch(() => {});
  console.log(JSON.stringify({
    url: await page.url(),
    title: await page.title(),
    text: (await page.evaluate(() => document.body.innerText)).slice(0, 3500),
    links: await page.evaluate(() =>
      [...document.querySelectorAll("a")].map((a) => ({
        text: a.innerText?.trim(),
        href: a.href,
      })).filter((x) => /login|register|data|download|join|files/i.test(x.text || x.href)).slice(0, 40),
    ),
  }));
}
