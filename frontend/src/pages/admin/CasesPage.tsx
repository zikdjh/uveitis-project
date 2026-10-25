import { ArrowRight } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listCases, type CaseRecord } from "@/api/cases";

export default function AdminCasesPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCases().then(setCases).catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : "病例记录加载失败"),
    );
  }, []);

  return (
    <section className="page">
      <div className="page-heading"><div><h1>病例审计</h1><p className="page-lead">查看病例处理与复核状态。</p></div></div>
      {error && <div className="notice error-notice">{error}</div>}
      <div className="case-table">
        {cases.map((item) => (
          <Link to={`/admin/cases/${item.id}`} key={item.id}>
            <div><strong>{item.complaint}</strong><small>{item.patient_age} 岁 · 建档 {new Date(item.created_at).toLocaleString("zh-CN")}</small></div>
            <span className={`status ${item.status}`}>{statusText[item.status]}</span><ArrowRight size={16} />
          </Link>
        ))}
        {!cases.length && <div className="empty-state"><p>暂无病例记录</p></div>}
      </div>
    </section>
  );
}

const statusText: Record<CaseRecord["status"], string> = {
  created: "待分析",
  analyzing: "分析中",
  awaiting_review: "待复核",
  reviewed: "已复核",
  failed: "分析失败",
};
