import { ArrowRight, ClipboardPlus, ShieldCheck, UserRound } from "lucide-react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listCases, type CaseRecord } from "@/api/cases";

export default function WorkbenchPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listCases()
      .then(setCases)
      .catch((reason: unknown) =>
        setError(reason instanceof Error ? reason.message : "工作台加载失败"),
      );
  }, []);

  const pending = cases.filter((item) => item.status === "awaiting_review");
  const inProgress = cases.filter((item) => item.status === "analyzing");
  const reviewed = cases.filter((item) => item.status === "reviewed");

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
        <Metric label="待复核" value={pending.length} note="需要医生判断" />
        <Metric label="分析中" value={inProgress.length} note="正在处理" />
        <Metric label="已复核" value={reviewed.length} note="已完成记录" />
        <Metric label="全部病例" value={cases.length} note="当前工作区" />
      </div>
      <div className="workbench-grid">
        <section className="panel">
          <div className="section-heading">
            <div><h2>待复核病例</h2><span>优先处理最近更新的病例</span></div>
            <ShieldCheck size={20} />
          </div>
          <div className="case-table compact">
            {pending.slice(0, 6).map((item) => (
              <Link to={`/doctor/cases/${item.id}/review`} key={item.id}>
                <div><strong>{item.patient_age} 岁 · {item.complaint}</strong><small>{new Date(item.updated_at).toLocaleString("zh-CN")}</small></div>
                <ArrowRight size={16} />
              </Link>
            ))}
            {!pending.length && <div className="empty-state"><UserRound size={24} /><p>暂无待复核病例</p><span>分析完成的病例会显示在这里。</span></div>}
          </div>
          <Link className="text-link" to="/doctor/reviews">查看全部待复核 <ArrowRight size={14} /></Link>
        </section>
        <section className="panel">
          <div className="section-heading"><div><h2>最近记录</h2><span>最近更新的病例</span></div></div>
          <div className="case-table compact">
            {cases.slice(0, 5).map((item) => (
              <Link to={`/doctor/cases/${item.id}/summary`} key={item.id}>
                <div><strong>{item.complaint}</strong><small>{statusText[item.status]} · {new Date(item.updated_at).toLocaleString("zh-CN")}</small></div>
                <ArrowRight size={16} />
              </Link>
            ))}
            {!cases.length && <div className="empty-state"><ClipboardPlus size={24} /><p>还没有病例</p><span>创建第一份病例开始记录。</span></div>}
          </div>
          <Link className="text-link" to="/doctor/cases">查看全部病例 <ArrowRight size={14} /></Link>
        </section>
      </div>
    </section>
  );
}

function Metric({ label, value, note }: { label: string; value: number; note: string }) {
  return <div className="metric-card"><span>{label}</span><strong>{value}</strong><small>{note}</small></div>;
}

const statusText: Record<CaseRecord["status"], string> = {
  created: "待分析",
  analyzing: "分析中",
  awaiting_review: "待复核",
  reviewed: "已复核",
  failed: "分析失败",
};
