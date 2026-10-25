const task = await takeOverTaskSpace(2);
const page = task.page("p1");

for (const url of [
  "https://www.kaggle.com/datasets/orvile/eye-diseases-classification",
  "https://www.kaggle.com/competitions/aptos2019-blindness-detection/rules",
]) {
  await page.goto(url, { timeout: 60_000 });
  await page.waitForLoadState("load", { timeout: 30_000 }).catch(() => {});
  await page.waitForTimeout(3_000);
  console.log(JSON.stringify({
    url: await page.url(),
    title: await page.title(),
    text: (await page.evaluate(() => document.body.innerText)).slice(0, 2500),
    buttons: await page.evaluate(() =>
      [...document.querySelectorAll("button")]
        .map((b) => b.innerText?.trim().replace(/\s+/g, " "))
        .filter(Boolean)
        .slice(0, 50),
    ),
  }));
}
