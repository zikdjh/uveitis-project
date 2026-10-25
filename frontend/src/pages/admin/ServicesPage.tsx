import { Activity, Database, Server } from "lucide-react";
import { useEffect, useState } from "react";

import { getSystemOverview, type SystemOverview } from "@/api/system";
import { request } from "@/api/client";

type Infrastructure = { postgres: boolean; redis: boolean };

export default function ServicesPage() {
  const [overview, setOverview] = useState<SystemOverview | null>(null);
  const [infrastructure, setInfrastructure] = useState<Infrastructure | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setError(null);
    try {
      const [overviewResult, infrastructureResult] = await Promise.all([
        getSystemOverview(),
        request<Infrastructure>("/api/v1/system/infrastructure"),
      ]);
      setOverview(overviewResult);
      setInfrastructure(infrastructureResult);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "服务状态加载失败");
    }
  }

  useEffect(() => { void load(); }, []);

  return (
    <section className="page">
      <div className="page-heading">
        <div><h1>服务状态</h1><p className="page-lead">检查数据库、会话存储与辅助分析服务。</p></div>
        <button className="button secondary" type="button" onClick={() => void load()}><Activity size={16} /> 刷新</button>
      </div>
      {error && <div className="notice error-notice">{error}</div>}
      <div className="service-grid">
        <ServiceStatus title="PostgreSQL" description="病例与账号数据" healthy={infrastructure?.postgres} icon={Database} />
        <ServiceStatus title="Redis" description="会话与待复核队列" healthy={infrastructure?.redis} icon={Server} />
      </div>
      {overview && (
        <section className="panel">
          <div className="section-heading"><div><h2>辅助服务</h2><span>仅供运行人员查看</span></div></div>
          <div className="boundary-list">{overview.models.map((model) => <div key={model.role}><span>{model.role}</span><strong>{model.enabled ? "可用" : "未启用"}</strong></div>)}</div>
        </section>
      )}
    </section>
  );
}

function ServiceStatus({ title, description, healthy, icon: Icon }: { title: string; description: string; healthy?: boolean; icon: typeof Database }) {
  return <div className="panel service-card"><Icon size={21} /><div><h2>{title}</h2><p>{description}</p></div><span className={healthy ? "service-ok" : "service-down"}>{healthy === undefined ? "检查中" : healthy ? "正常" : "异常"}</span></div>;
}
