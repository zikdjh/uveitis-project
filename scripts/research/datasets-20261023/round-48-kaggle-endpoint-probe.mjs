const task = await takeOverTaskSpace(2);
const page = task.page("p1");

const result = await page.evaluate(async () => {
  const paths = [
    "/api/v1/datasets/download/andrewmvd/ocular-disease-recognition-odir5k",
    "/api/v1/datasets/download/andrewmvd/ocular-disease-recognition-odir5k?datasetVersionNumber=1",
  ];
  const out = [];
  for (const path of paths) {
    const response = await fetch(path, { method: "GET", redirect: "manual" });
    out.push({
      path,
      status: response.status,
      type: response.type,
      redirected: response.redirected,
      url: response.url,
      contentType: response.headers.get("content-type"),
      contentLength: response.headers.get("content-length"),
      location: response.headers.get("location"),
    });
  }
  return out;
});
console.log(result);
