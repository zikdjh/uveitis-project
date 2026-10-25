const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.goto(
  "https://www.kaggle.com/settings/account?verifyPhone=1&verifyPhoneReturnUrl=https%3A%2F%2Fwww.kaggle.com%2Fdatasets%2Fandrewmvd%2Focular-disease-recognition-odir5k",
  { timeout: 60_000 },
);
await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
console.log({ url: await page.url(), title: await page.title() });
console.log(await page.snapshot());
await task.handOff();
