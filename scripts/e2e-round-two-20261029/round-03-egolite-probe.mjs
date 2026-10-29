// Round 3: re-check ego lite connectivity and resume the existing TaskSpace.
const NAME = "uveitis round two e2e 20261029";

const spaces = await listTaskSpaces();
console.log(
  JSON.stringify({
    spaces: spaces.map((s) => ({ id: s.id, name: s.name, ownership: s.ownership })),
  }),
);

const task = await taskSpace(NAME);
console.log({ spaceId: task.spaceId, name: task.name, ownership: task.ownership });

const tabs = await task.tabs();
console.log(
  JSON.stringify(
    tabs.map((t) => ({
      label: t.label ?? null,
      title: t.title,
      url: t.url,
      active: t.active,
      openedBy: t.openedBy,
    })),
  ),
);

const page = task.page("p1");
await page.goto("http://127.0.0.1:5173/admin/login");
await page.waitForLoadState();
console.log({ url: await page.url(), title: await page.title() });

const shot = await page.screenshot({ path: "D:/temp/gpt/uveitis-project/scripts/e2e-round-two-20261029/shot-r03-admin-login.png" });
console.log({ screenshot: shot });
