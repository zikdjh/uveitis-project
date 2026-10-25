const task = await takeOverTaskSpace(2);
const page = task.page("p1");

const downloadPromise = page.waitForEvent("download", { timeout: 180_000 });
const receipt = await page.click("text=Download dataset as zip");
console.log({ clickReceipt: receipt });

try {
  const download = await downloadPromise;
  const savePath =
    "D:/temp/gpt/uveitis-project/datasets/p0/kaggle-odir-5k/" +
    download.suggestedFilename();
  await download.saveAs(savePath);
  console.log({
    downloadUrl: download.url(),
    suggestedFilename: download.suggestedFilename(),
    savedTo: savePath,
    failure: await download.failure(),
  });
} catch (error) {
  console.log({
    downloadWaitError: error.message,
    currentUrl: await page.url(),
    currentTitle: await page.title(),
  });
  console.log(await page.snapshot());
}
