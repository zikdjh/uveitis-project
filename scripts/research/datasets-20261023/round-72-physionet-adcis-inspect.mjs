const task = await takeOverTaskSpace(2);
const page = task.page("p1");
for (const url of [
  "https://physionet.org/content/brazilian-ophthalmological/",
  "https://www.adcis.net/en/Download-Third-Party/Messidor.html",
]) {
  await page.goto(url, { timeout: 60_000 });
  await page.waitForLoadState("load", { timeout: 30_000 }).catch(() => {});
  console.log(JSON.stringify({
    url: await page.url(),
    title: await page.title(),
    text: (await page.evaluate(() => document.body.innerText)).slice(0, 5000),
    links: await page.evaluate(() =>
      [...document.querySelectorAll("a")].map((a) => ({
        text: a.innerText?.trim(),
        href: a.href,
      })).filter((x) => /login|sign.?in|register|download|zip|license|agreement|accept|files/i.test(x.text || x.href)).slice(0, 60),
      ),
  }));
}
