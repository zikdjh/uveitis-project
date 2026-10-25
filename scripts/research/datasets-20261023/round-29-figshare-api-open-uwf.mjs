const task = await taskSpace("uveitis figshare downloads 20261024");
const page = task.page("p1");

await page.goto("https://api.figshare.com/v2/articles/26936446", { timeout: 45_000 });
await page.waitForLoadState("load");

const raw = await page.evaluate(() => document.body.innerText.slice(0, 3000));
console.log({ url: await page.url(), title: await page.title(), raw });
