import { ArrowRight, ClipboardPlus, ShieldCheck, UserRound } from "lucide-react";
import { Pagination } from "antd";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listCases, type CaseRecord } from "@/api/cases";
import { getSystemOverview } from "@/api/system";

export default function WorkbenchPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [counts, setCounts] = useState({ total: 0, analyzing: 0, awaiting_review: 0, reviewed: 0 });
  const [pendingTotal, setPendingTotal] = useState(0);
  const [pendingPage, setPendingPage] = useState(1);
  const [pendingPageSize, setPendingPageSize] = useState(8);

  useEffect(() => {
    Promise.all([
      listCases({ status: "awaiting_review", page: pendingPage, page_size: pendingPageSize }),
      getSystemOverview(),
    ])
      .then(([result, overview]) => {
        setCases(result.items);
        setPendingTotal(result.total);
        setCounts(overview.stats);
      })
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "工作台加载失败"),
      );
  }, [pendingPage, pendingPageSize]);

  const pendingPageCount = Math.max(1, Math.ceil(pendingTotal / pendingPageSize));

  useEffect(() => {
    setPendingPage((current) => Math.min(current, pendingPageCount));
  }, [pendingPageCount]);

  return (
    <section className="page">
      <div className="page-heading">
        <div>
          <h1>工作台</h1>
          <p className="page-lead">从待复核病例开始，完成今天的临床记录。</p>
        </div>
        <Link className="button primary" to="/doctor/cases/new">
          <ClipboardPlus size={16} /> 新建病例
        </Link>
      </div>
      {error && <div className="notice error-notice">{error}</div>}
      <div className="metric-grid">
        <Metric label="待复核" value={counts.awaiting_review} note="需要医生判断" />
        <Metric label="分析中" value={counts.analyzing} note="正在处理" />
        <Metric label="已复核" value={counts.reviewed} note="已完成记录" />
        <Metric label="全部病例" value={counts.total} note="当前工作区" />
      </div>
      <div className="workbench-grid workbench-review">
        <section className="panel">
          <div className="section-heading">
            <div><h2>待复核病例</h2></div>
            <ShieldCheck size={20} />
          </div>
          <div className="case-table compact">
            {cases.map((item) => (
              <Link to={`/doctor/cases/${item.id}/review`} key={item.id}>
                <div><strong>{item.patient_age} 岁 · {item.complaint}</strong><small>{new Date(item.updated_at).toLocaleString("zh-CN")}</small></div>
                <ArrowRight size={16} />
              </Link>
            ))}
            {!pendingTotal && <div className="empty-state"><UserRound size={24} /><p>暂无待复核病例</p><span>分析完成的病例会显示在这里。</span></div>}
          </div>
          <div className="workbench-review-footer">
            <Link className="text-link" to="/doctor/cases?status=awaiting_review">查看全部待复核 <ArrowRight size={14} /></Link>
            {pendingTotal > 0 && (
              <Pagination
                current={pendingPage}
                pageSize={pendingPageSize}
                total={pendingTotal}
                showSizeChanger
                pageSizeOptions={[8, 16, 32]}
                showTotal={(total) => `共 ${total} 例`}
                onChange={(page, pageSize) => {
                  const pageSizeChanged = pageSize !== pendingPageSize;
                  setPendingPageSize(pageSize);
                  setPendingPage(pageSizeChanged ? 1 : page);
                }}
              />
            )}
          </div>
        </section>
      </div>
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: number; note: string }) {
  return <div className="metric-card"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>;
}
