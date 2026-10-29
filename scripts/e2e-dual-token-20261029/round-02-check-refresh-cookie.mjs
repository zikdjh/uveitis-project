const task = await taskSpace("dual token browser verification 20261029");
const page = task.page("p1");

const allCookies = await page.cdp("Network.getAllCookies");
const authCookies = allCookies.cookies
  .filter((c) => c.name.startsWith("uveitis_"))
  .map((c) => ({ name: c.name, path: c.path, domain: c.domain, expires: c.expires }));

const url = await page.url();
console.log({ url, authCookies });
