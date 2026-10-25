const task = await takeOverTaskSpace(2);
const page = task.page("p1");

const snapshot = await page.snapshot({ scope: "full_page" });
console.log(snapshot);
