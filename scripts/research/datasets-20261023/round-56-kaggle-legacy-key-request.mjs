const task = await takeOverTaskSpace(2);
const page = task.page("p1");

const downloadPromise = page.waitForEvent("download", { timeout: 60_000 });
await page.click("text=Create Legacy API Key");

try {
  const download = await downloadPromise;
  const savePath = "D:/temp/gpt/uveitis-project/.kaggle/kaggle.json";
  await download.saveAs(savePath);
  console.log({
    savedTo: savePath,
    file: download.suggestedFilename(),
    failure: await download.failure(),
  });
} catch (error) {
  console.log({ error: error.message });
  console.log(await page.evaluate(() => document.body.innerText.slice(0, 2500)));
  await task.handOff();
}
