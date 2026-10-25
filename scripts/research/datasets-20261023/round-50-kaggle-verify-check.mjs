const task = await takeOverTaskSpace(2);
const page = task.page("p1");
console.log({ url: await page.url(), title: await page.title() });

const status = await page.evaluate(() => ({
  bodyText: document.body.innerText.slice(0, 4000),
}));
console.log(status);
