const task = await taskSpace(1);
const page = task.page("p1");

const targets = [
  "https://api.datacite.org/dois?query=uveitis%20OCT&page[size]=100",
  "https://api.datacite.org/dois?query=uveitis%20optical%20coherence%20tomography&page[size]=100",
  "https://zenodo.org/api/records?q=uveitis%20OCT&size=100",
  "https://zenodo.org/api/records?q=uveitis%20optical%20coherence%20tomography&size=100",
  "https://api.figshare.com/v2/articles/search",
];

for (const [index, target] of targets.entries()) {
  try {
    if (target.includes("figshare")) {
      const response = await page.fetch(target, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ search_for: "uveitis OCT", page_size: 100 }),
        timeout: 30000,
      });
      const data = JSON.parse(response.body);
      console.log(JSON.stringify({
        target,
        status: response.status,
        total: data.length,
        items: data.slice(0, 60).map((item) => ({
          id: item.id, title: item.title, doi: item.doi, url: item.url_public, published: item.published_date,
        })),
      }, null, 2));
      continue;
    }
    const response = await page.fetch(target, { timeout: 30000 });
    const data = JSON.parse(response.body);
    if (target.includes("datacite")) {
      const items = data.data || [];
      console.log(JSON.stringify({
        target,
        status: response.status,
        total: data.meta?.total,
        items: items.map((item) => ({
          doi: item.id,
          title: item.attributes?.titles?.[0]?.title,
          rights: item.attributes?.rightsList,
          types: item.attributes?.types,
          url: item.attributes?.url,
          publisher: item.attributes?.publisher,
          year: item.attributes?.publicationYear,
        })),
      }, null, 2));
    } else {
      const hits = data.hits?.hits || [];
      console.log(JSON.stringify({
        target,
        status: response.status,
        total: data.hits?.total,
        items: hits.map((item) => ({
          id: item.id,
          doi: item.doi,
          title: item.metadata?.title,
          access: item.metadata?.access_right,
          license: item.metadata?.license,
          publication_date: item.metadata?.publication_date,
          files: item.files?.map((f) => ({ key: f.key, size: f.size })),
          links: item.links,
        })),
      }, null, 2));
    }
  } catch (error) {
    console.log(JSON.stringify({ target, error: String(error) }));
  }
}
