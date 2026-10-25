import { ArrowRight, CheckCircle2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listCases, type CaseRecord } from "@/api/cases";

export default function ReviewQueuePage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCases()
      .then((items) => setCases(items.filter((item) => item.status === "awaiting_review")))
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "待复核列表加载失败"),
      );
  }, []);

  return (
    <section className="page">
      <div className="page-heading">
        <div><h1>待复核</h1><p className="page-lead">按更新时间排列，进入病例后完成最终判断。</p></div>
      </div>
      {error && <div className="notice error-notice">{error}</div>}
      <div className="case-table">
        {cases.map((item) => (
          <Link to={`/doctor/cases/${item.id}/review`} key={item.id}>
            <div><strong>{item.patient_age} 岁 · {item.complaint}</strong><small>{new Date(item.updated_at).toLocaleString("zh-CN")}</small></div>
            <span className="status awaiting_review">待复核</span><ArrowRight size={16} />
          </Link>
        ))}
        {!error && cases.length === 0 && (
          <div className="empty-state">
            <CheckCircle2 size={26} /><p>暂无待复核病例</p><span>分析完成后的病例会出现在这里。</span>
          </div>
        )}
      </div>
    </section>
  );
}
