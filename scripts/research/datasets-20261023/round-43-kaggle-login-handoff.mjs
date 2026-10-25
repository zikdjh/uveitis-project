const task = await taskSpace("uveitis login downloads 20261024");
const page = task.page("p1");

const returnUrl = "https://www.kaggle.com/datasets/andrewmvd/ocular-disease-recognition-odir5k";
await page.goto(
  `https://www.kaggle.com/account/login?returnUrl=${encodeURIComponent(returnUrl)}`,
  { timeout: 60_000 },
);
await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});

console.log({
  spaceId: task.spaceId,
  page: page.label,
  url: await page.url(),
  title: await page.title(),
});
console.log(await page.snapshot());

await task.handOff();
