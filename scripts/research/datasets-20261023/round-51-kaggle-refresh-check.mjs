const task = await takeOverTaskSpace(2);
const page = task.page("p1");
await page.reload({ timeout: 60_000 });
await page.waitForLoadState("domcontentloaded", { timeout: 30_000 }).catch(() => {});
const text = await page.evaluate(() => document.body.innerText);
console.log({
  url: await page.url(),
  title: await page.title(),
  phoneVerified: !text.includes("Your account is not verified"),
  hasVerifyDialog: text.includes("Just one thing—first verify your account"),
  hasPhoneVerifiedText: /Phone verification[\s\S]{0,200}verified/i.test(text),
});
