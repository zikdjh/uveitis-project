const task = await takeOverTaskSpace(2);
const pages = await task.pages();
console.log({
  spaceId: task.spaceId,
  pages: pages.map((page) => page.label),
});

const tabs = await task.tabs();
console.log(tabs.map(({ label, title, url, active, openedBy }) => ({
  label,
  title,
  url,
  active,
  openedBy,
})));

const page = task.userPage();
console.log({
  page: page.label,
  url: await page.url(),
  title: await page.title(),
});
console.log(await page.snapshot());
