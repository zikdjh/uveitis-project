const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto("https://physionet.org/login/", {
  timeout: 60_000,
  waitUntil: "domcontentloaded",
}).catch((e) => console.log({ gotoWarning: e.message }));
await page.waitForLoadState("domcontentloaded", { timeout: 20_000 }).catch(() => {});
console.log({ url: await page.url(), title: await page.title() });
console.log(await page.snapshot());
await task.handOff();
