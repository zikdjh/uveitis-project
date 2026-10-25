import { ArrowRight, ClipboardPlus, FileImage } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listCases, type CaseRecord } from "@/api/cases";

export default function CaseListPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCases()
      .then(setCases)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "病例列表加载失败"),
      );
  }, []);

  return (
    <section className="page">
      <div className="page-heading">
        <div>
          <h1>病例</h1>
          <p className="page-lead">查看病例资料、辅助结果和复核状态。</p>
        </div>
        <Link className="button primary" to="/doctor/cases/new">
          <ClipboardPlus size={16} /> 新建病例
        </Link>
      </div>
      {error && <div className="notice error-notice">{error}</div>}
      <div className="case-table">
        {cases.map((item) => (
          <Link to={`/doctor/cases/${item.id}/summary`} key={item.id}>
            <div>
              <strong>{item.patient_age} 岁 · {sexText[item.patient_sex]}</strong>
              <p>{item.complaint}</p>
              <small>{new Date(item.updated_at).toLocaleString("zh-CN")} · {item.images.length} 张影像</small>
            </div>
            <span className={`status ${item.status}`}>{statusText[item.status]}</span>
            <ArrowRight size={16} />
          </Link>
        ))}
        {!error && cases.length === 0 && (
          <div className="empty-state">
            <FileImage size={26} /><p>还没有病例</p><span>从右上角新建第一份病例。</span>
          </div>
        )}
      </div>
    </section>
  );
}

const sexText = { F: "女", M: "男", U: "未说明" };
const statusText: Record<CaseRecord["status"], string> = {
  created: "待分析",
  analyzing: "分析中",
  awaiting_review: "待复核",
  reviewed: "已复核",
  failed: "分析失败",
};
