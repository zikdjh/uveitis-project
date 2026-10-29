import {
  AlertCircle,
  Boxes,
  CheckCircle2,
  CircleDashed,
  Database,
  LoaderCircle,
  RefreshCw,
  Server,
  ShieldCheck,
} from "lucide-react";
import { useEffect, useState } from "react";

import { getSystemOverview, type SystemOverview } from "@/api/system";

const statusLabel = { mock: "运行中", configured: "运行中", offline: "未启用" };

export default function AdminPage() {
  const [overview, setOverview] = useState<SystemOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setOverview(await getSystemOverview());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "系统状态加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <section className="page">
      <div className="page-heading">
        <div>
          <h1>运行状态</h1>
          <p className="page-lead">病例处理状态与服务可用性。</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void refresh()} disabled={loading}>
          <RefreshCw size={16} className={loading ? "spin" : ""} /> 刷新状态
        </button>
      </div>

      {error && (
        <div className="notice error-notice" role="alert">
          <AlertCircle size={17} /> {error}
        </div>
      )}

      {loading && !overview ? (
        <div className="panel loading-panel">
          <LoaderCircle className="spin" size={24} />
          <span>正在读取系统状态</span>
        </div>
      ) : overview ? (
        <>
          <div className="metric-grid">
            <Metric icon={Database} label="病例总数" value={overview.stats.total} note="当前工作区" />
            <Metric icon={LoaderCircle} label="分析中" value={overview.stats.analyzing} note="正在处理" />
            <Metric icon={CircleDashed} label="待复核" value={overview.stats.awaiting_review} note="等待医生判断" />
            <Metric icon={CheckCircle2} label="已复核" value={overview.stats.reviewed} note="记录已确认" />
          </div>

          <div className="admin-grid">
            <section className="panel admin-boundary-panel">
              <div className="section-heading">
                <div><h2>服务状态</h2><span>辅助分析与检索服务</span></div>
                <Boxes size={20} />
              </div>
              <div className="model-list">
                {overview.models.map((model) => (
                  <div className="model-row" key={model.role}>
                    <div className="model-icon"><Server size={17} /></div>
                    <div className="model-name">
                      <span>{model.role}</span>
                      <strong title={model.name}>{model.name}</strong>
                    </div>
                    <span className={`model-status ${model.enabled ? model.status : "optional"}`}>
                      {model.enabled ? statusLabel[model.status] : "未启用"}
                    </span>
                  </div>
                ))}
              </div>
              <div className="inline-note">
                <ShieldCheck size={16} />
                <span>
                  服务状态仅用于运行管理；医疗结论仍须结合原始资料由医生复核。
                </span>
              </div>
            </section>

            <section className="panel">
              <div className="section-heading">
                <div><h2>使用边界</h2><span>记录与复核规则</span></div>
                <ShieldCheck size={20} />
              </div>
              <div className="boundary-list">
                <Boundary title="病例资料" value="本地保存" />
                <Boundary title="辅助分析" value="不直接形成医疗结论" />
                <Boundary title="最终决策" value="医生复核" />
              </div>
              <p className="disclaimer">{overview.disclaimer}</p>
            </section>
          </div>

        </>
      ) : null}
    </section>
  );
}

function Metric({
  icon: Icon,
  label,
  value,
  note,
}: {
  icon: typeof Database;
  label: string;
  value: number;
  note: string;
}) {
  return (
    <div className="metric-card">
      <div className="metric-icon"><Icon size={18} /></div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function Boundary({ title, value }: { title: string; value: string }) {
  return <div><span>{title}</span><strong>{value}</strong></div>;
}
