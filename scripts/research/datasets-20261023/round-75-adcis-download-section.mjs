const task = await takeOverTaskSpace(2);
const page = task.page("p1");
const buttons = await page.evaluate(() =>
  [...document.querySelectorAll("button, summary, a")].map((n) => ({
    tag: n.tagName,
    text: n.innerText?.trim().slice(0, 120),
    aria: n.getAttribute("aria-label"),
    href: n.href,
  })).filter((x) => /download|information|accordion|expand/i.test(x.text || x.aria || x.href || "")),
);
console.log(buttons);
