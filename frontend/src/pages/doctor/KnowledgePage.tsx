import { BookOpenCheck, LoaderCircle, SearchX } from "lucide-react";
import { type FormEvent, useState } from "react";

import { request } from "@/api/client";

type Match = {
  document: { id: string; title: string; content: string; source: string };
  score: number;
};

export default function KnowledgePage() {
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Match[]>([]);
  const [searching, setSearching] = useState(false);
  const [searched, setSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) return;
    setError(null);
    setSearching(true);
    setSearched(true);
    try {
      setMatches(await request<Match[]>("/api/v1/knowledge/search", {
        method: "POST",
        body: JSON.stringify({ query, top_k: 8 }),
      }));
    } catch (reason) {
      setMatches([]);
      setError(reason instanceof Error ? reason.message : "检索失败");
    } finally {
      setSearching(false);
    }
  }

  return (
    <section className="page">
      <div className="page-heading">
        <div><h1>临床知识</h1><p className="page-lead">检索指南、文献与病例资料，引用前请核对来源。</p></div>
      </div>
      <form className="knowledge-search" onSubmit={(event) => void search(event)}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入临床问题或关键词" />
        <button className="button primary" type="submit">检索</button>
      </form>
      {error && <div className="notice error-notice">{error}</div>}
      <div className="knowledge-results">
        {searching && <div className="loading-panel"><LoaderCircle className="spin" size={22} /> 正在检索知识库</div>}
        {matches.map((item) => (
          <article key={item.document.id}>
            <BookOpenCheck size={19} />
            <div>
              <h2>{item.document.title}</h2>
              <p>{item.document.content}</p>
              <small>{item.document.source || "未标注来源"} · 相关度 {Math.round(item.score * 100)}%</small>
            </div>
          </article>
        ))}
        {searched && !searching && !matches.length && !error && (
          <div className="empty-state">
            <SearchX size={26} />
            <p>没有匹配的检索结果</p>
            <span>请更换关键词重试，或联系管理员补充知识文档。</span>
          </div>
        )}
      </div>
    </section>
  );
}
