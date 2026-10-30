import { RefreshCw, Waypoints } from "lucide-react";
import { Tag } from "antd";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { listAnalysisJobs, type AnalysisQueueRecord } from "@/api/cases";

const jobStatusText: Record<AnalysisQueueRecord["job_status"], string> = {
  queued: "排队中",
  running: "执行中",
  finalizing: "写入结果",
  completed: "已完成",
  failed: "失败",
};

const jobStatusColor: Record<AnalysisQueueRecord["job_status"], string> = {
  queued: "gold",
  running: "processing",
  finalizing: "processing",
  completed: "success",
  failed: "error",
};

function jobTarget(role: "doctor" | "admin", caseId: string): string {
  return role === "admin" ? `/admin/cases/${caseId}` : `/doctor/cases/${caseId}/analysis`;
}

export default function AnalysisQueuePanel({ role }: { role: "doctor" | "admin" }) {
  const [jobs, setJobs] = useState<AnalysisQueueRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await listAnalysisJobs(50);
      setJobs(data);
      setError(null);
    } catch (reason: unknown) {
      setError(reason instanceof Error ? reason.message : "分析队列加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const hasActive = jobs.some(
    (job) => job.job_status === "queued" || job.job_status === "running" || job.job_status === "finalizing",
  );

  useEffect(() => {
    const interval = window.setInterval(() => void load(), hasActive ? 4000 : 15000);
    return () => window.clearInterval(interval);
  }, [hasActive, load]);

  return (
    <section className="panel analysis-queue-panel">
      <div className="section-heading">
        <div>
          <h2>分析队列</h2>
          <span>{hasActive ? "任务执行中，自动刷新" : "空闲状态，自动轮询"}</span>
        </div>
        <button className="button secondary" type="button" onClick={() => void load()} disabled={loading}>
          <RefreshCw size={16} className={loading ? "spin" : ""} /> 刷新
        </button>
      </div>
      {error && <div className="notice error-notice" role="alert">{error}</div>}
      <div className="case-table compact">
        {jobs.map((job) => (
          <Link key={job.job_id} to={jobTarget(role, job.case_id)}>
            <div>
              <strong>{job.complaint || "未填写主诉"}</strong>
              <small>
                {job.patient_age != null ? `${job.patient_age} 岁 · ` : ""}
                {new Date(job.created_at).toLocaleString("zh-CN")}
                {role === "admin" && job.owner_name ? ` · ${job.owner_name}` : ""}
                {job.attempt_count > 1 ? ` · 第 ${job.attempt_count} 次尝试` : ""}
                {job.job_status === "failed" && job.error ? ` · ${job.error}` : ""}
              </small>
            </div>
            <Tag color={jobStatusColor[job.job_status]}>{jobStatusText[job.job_status]}</Tag>
          </Link>
        ))}
        {loading && !jobs.length && (
          <div className="loading-panel"><RefreshCw className="spin" size={20} /> 正在读取分析队列</div>
        )}
        {!loading && !error && !jobs.length && (
          <div className="empty-state"><Waypoints size={24} /><p>暂无分析任务</p><span>提交辅助分析后，任务会排队并在这里展示进度。</span></div>
        )}
      </div>
    </section>
  );
}
