import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { getCase, type CaseRecord } from "@/api/cases";

export default function AdminCaseDetailPage() {
  const { caseId = "" } = useParams();
  const [item, setItem] = useState<CaseRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getCase(caseId).then(setItem).catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : "病例加载失败"),
    );
  }, [caseId]);

  return (
    <section className="page">
      <div className="page-heading">
        <div><h1>病例处理记录</h1><p className="page-lead">仅用于运行审计，不在此处修改医疗结论。</p></div>
        <Link className="button secondary" to="/admin/cases">返回列表</Link>
      </div>
      {error && <div className="notice error-notice">{error}</div>}
      {item && (
        <section className="panel">
          <div className="clinical-facts">
            <div><span>状态</span><strong>{item.status}</strong></div>
            <div><span>影像</span><strong>{item.images.length} 张</strong></div>
            <div><span>更新</span><strong>{new Date(item.updated_at).toLocaleString("zh-CN")}</strong></div>
          </div>
          <div className="clinical-text"><span>主诉</span><p>{item.complaint}</p></div>
          <div className="clinical-text"><span>复核</span><p>{item.review ? `${item.review.reviewer} · ${new Date(item.review.reviewed_at).toLocaleString("zh-CN")}` : "尚未完成"}</p></div>
        </section>
      )}
    </section>
  );
}
