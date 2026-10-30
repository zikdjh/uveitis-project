import { CheckCircle2, FileText, LoaderCircle } from "lucide-react";
import { type FormEvent, useState } from "react";

import { request } from "@/api/client";
import { PageHeader, PageSection } from "@/components/ui";

export default function AdminKnowledgePage() {
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setError(null);
    setNotice(null);
    setBusy(true);
    try {
      await request("/api/v1/knowledge/documents", {
        method: "POST",
        body: JSON.stringify({
          title: String(form.get("title") ?? ""),
          content: String(form.get("content") ?? ""),
          source: String(form.get("source") ?? ""),
          category: String(form.get("category") ?? "other"),
        }),
      });
      formElement.reset();
      setNotice("知识文档已建立索引。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "知识文档保存失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <PageHeader title="知识库" description="维护医生检索使用的指南、文献和病例资料。" />
      {error && <div className="notice error-notice">{error}</div>}
      {notice && <div className="notice success-notice"><CheckCircle2 size={17} /> {notice}</div>}
      <PageSection title="新增知识文档" description="保存后可被临床知识检索引用" icon={FileText}>
        <form className="form-grid" onSubmit={(event) => void submit(event)}>
          <label className="span-2">标题<input name="title" required maxLength={300} /></label>
          <label>分类<select name="category" defaultValue="guideline"><option value="guideline">临床指南</option><option value="literature">文献</option><option value="case">病例资料</option><option value="other">其他</option></select></label>
          <label>来源<input name="source" maxLength={1000} placeholder="机构、期刊或链接" /></label>
          <label className="span-2">正文<textarea name="content" required minLength={2} maxLength={20000} /></label>
      <div className="form-actions span-2"><button className="button primary" type="submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16} /> : <FileText size={16} />} 保存并建立索引</button></div>
        </form>
      </PageSection>
    </section>
  );
}
