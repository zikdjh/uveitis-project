import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ClipboardPlus,
  FileImage,
  ExternalLink,
  LoaderCircle,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { type ChangeEvent, type FormEvent, useContext, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiUrl } from "@/api/client";
import {
  analyzeCase,
  createCase,
  reviewCase,
  uploadCaseImages,
  type CaseCreateInput,
  type ImageKind,
  type ReviewInput,
} from "@/api/cases";
import { CaseContext } from "@/pages/doctor/CaseContext";

const sexText = { F: "女", M: "男", U: "未说明" };
const eyeText = { OD: "右眼", OS: "左眼", OU: "双眼", UNKNOWN: "未确认" };

function shortUrl(url: string): string {
  try {
    const parsed = new URL(url);
    const text = `${parsed.hostname}${parsed.pathname === "/" ? "" : parsed.pathname}`;
    return text.length <= 44 ? text : `${text.slice(0, 43)}…`;
  } catch {
    return url;
  }
}
const imageKindText = {
  fundus: "眼底",
  ultrawide: "超广角",
  oct: "OCT",
  anterior: "眼前段",
  other: "其他",
};

export function NewCasePage() {
  const navigate = useNavigate();
  const [form, setForm] = useState<CaseCreateInput>({
    patient_age: 40,
    patient_sex: "F",
    complaint: "",
    medical_history: "",
    affected_eye: "UNKNOWN",
    consent_confirmed: false,
  });
  const [files, setFiles] = useState<File[]>([]);
  const [imageKind, setImageKind] = useState<ImageKind>("fundus");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      let item = await createCase(form);
      if (files.length) item = await uploadCaseImages(item.id, files, imageKind);
      navigate(`/doctor/cases/${item.id}/summary`);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "病例创建失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <div className="page-heading">
        <div>
          <h1>新建病例</h1>
          <p className="page-lead">录入必要的临床资料，不填写不必要的身份信息。</p>
        </div>
      </div>
      {error && <div className="notice error-notice"><AlertCircle size={17} /> {error}</div>}
      <form className="panel" onSubmit={(event) => void submit(event)}>
        <div className="form-grid">
          <label>年龄<input type="number" min="0" max="130" required value={form.patient_age} onChange={(event) => setForm({ ...form, patient_age: Number(event.target.value) })} /></label>
          <label>性别<select value={form.patient_sex} onChange={(event) => setForm({ ...form, patient_sex: event.target.value as CaseCreateInput["patient_sex"] })}><option value="F">女</option><option value="M">男</option><option value="U">未说明</option></select></label>
          <label>患眼<select value={form.affected_eye} onChange={(event) => setForm({ ...form, affected_eye: event.target.value as CaseCreateInput["affected_eye"] })}><option value="UNKNOWN">未确认</option><option value="OD">右眼</option><option value="OS">左眼</option><option value="OU">双眼</option></select></label>
          <label>影像类型<select value={imageKind} onChange={(event) => setImageKind(event.target.value as ImageKind)}><option value="fundus">眼底</option><option value="ultrawide">超广角</option><option value="oct">OCT</option><option value="anterior">眼前段</option><option value="other">其他</option></select></label>
          <label className="span-2">主诉<textarea required minLength={2} maxLength={2000} value={form.complaint} onChange={(event) => setForm({ ...form, complaint: event.target.value })} placeholder="例如：左眼视物模糊伴眼前黑影三天" /></label>
          <label className="span-2">病史与已有检查<textarea maxLength={4000} value={form.medical_history} onChange={(event) => setForm({ ...form, medical_history: event.target.value })} placeholder="既往史、用药、实验室检查等" /></label>
          <label className="file-input span-2"><Upload size={18} /><span>{files.length ? `已选择 ${files.length} 个文件` : "添加影像（PNG / JPEG / TIFF，单张不超过 25 MB）"}</span><input type="file" multiple accept=".png,.jpg,.jpeg,.tif,.tiff" onChange={(event: ChangeEvent<HTMLInputElement>) => setFiles(Array.from(event.target.files ?? []))} /></label>
          <label className="checkbox-row span-2"><input type="checkbox" checked={form.consent_confirmed} onChange={(event) => setForm({ ...form, consent_confirmed: event.target.checked })} required /><span>我确认已获得病例资料用于辅助分析的必要授权。</span></label>
        </div>
        <div className="form-actions"><button className="button primary" type="submit" disabled={busy || !form.consent_confirmed}>{busy ? <LoaderCircle className="spin" size={16} /> : <ClipboardPlus size={16} />} 创建病例</button></div>
      </form>
    </section>
  );
}

export function CaseSummaryPage() {
  const { item } = useCase();
  return (
    <div className="case-panel-grid">
      <section className="panel">
        <div className="clinical-facts">
          <div><span>患者</span><strong>{item.patient_age} 岁 · {sexText[item.patient_sex]}</strong></div>
          <div><span>患眼</span><strong>{eyeText[item.affected_eye]}</strong></div>
          <div><span>影像</span><strong>{item.images.length} 张</strong></div>
        </div>
        <div className="clinical-text"><span>主诉</span><p>{item.complaint}</p></div>
        <div className="clinical-text"><span>病史与检查</span><p>{item.medical_history || "未填写"}</p></div>
        <p className="case-record-meta">建档 {new Date(item.created_at).toLocaleString("zh-CN")} · 更新 {new Date(item.updated_at).toLocaleString("zh-CN")}</p>
      </section>
      <section className="panel case-next-step">
        <h2>下一步</h2>
        <p>先核对病例资料与影像，再启动辅助分析。</p>
        <a className="button secondary" href="images"><FileImage size={16} /> 查看影像</a>
        <a className="button secondary" href="analysis"><ArrowRight size={16} /> 辅助分析</a>
      </section>
    </div>
  );
}

export function CaseImagesPage() {
  const { item } = useCase();
  return (
    <section className="panel">
      <div className="section-heading"><div><h2>影像</h2><span>{item.images.length} 个文件</span></div><FileImage size={20} /></div>
      {item.images.length ? <div className="image-list case-image-list">{item.images.map((image) => <a href={apiUrl(image.url)} target="_blank" rel="noreferrer" key={image.id}><FileImage size={18} /><span>{image.filename}</span><small>{imageKindText[image.kind]} · {(image.size_bytes / 1024 / 1024).toFixed(1)} MB</small></a>)}</div> : <div className="empty-state"><FileImage size={26} /><p>暂无影像</p><span>本病例可继续使用文本资料。</span></div>}
    </section>
  );
}

export function CaseAnalysisPage() {
  const { item, setItem, analysisJob, setAnalysisJob } = useCase();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function analyze() {
    setBusy(true);
    setError(null);
    try {
      const current = await analyzeCase(item.id);
      setItem(current);
      setAnalysisJob(null);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分析启动失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="section-heading"><div><h2>辅助分析</h2><span>分析结果须结合原始资料判断</span></div><ShieldCheck size={20} /></div>
      {error && <div className="notice error-notice">{error}</div>}
      {analysisJob?.error && <div className="notice error-notice">上次任务错误：{analysisJob.error}</div>}
      {item.analysis ? (
        <>
          <div className="analysis-summary">
            <div><span>状态</span><strong>{analysisJob ? jobStatusText[analysisJob.status] : analysisText[item.analysis.status]}</strong></div>
            <div><span>执行尝试</span><strong>{analysisJob ? `${analysisJob.attempt_count}/${analysisJob.max_attempts}` : "1/1"}</strong></div>
            <div><span>完成时间</span><strong>{item.analysis.completed_at ? new Date(item.analysis.completed_at).toLocaleString("zh-CN") : "处理中"}</strong></div>
          </div>
          {item.analysis.impression ? (
            <div className="result-box"><span>模型初判</span><p>{item.analysis.impression}</p></div>
          ) : (
            <p className="analysis-placeholder">本次未生成临床结论，请结合原始影像和检查资料判断。</p>
          )}
          {item.analysis.summary && <div className="result-box"><span>汇总梳理</span><p>{item.analysis.summary}</p></div>}
          {item.analysis.recommendations.length > 0 && (
            <div className="result-box">
              <span>下一步建议</span>
              <ul>{item.analysis.recommendations.map((text) => <li key={text}>{text}</li>)}</ul>
            </div>
          )}
          {item.analysis.web_evidence.length > 0 && (
            <div className="result-box">
              <span>网络辅助来源</span>
              <ul>
                {item.analysis.web_evidence.map((source) => (
                  <li key={source.url}>
                    <a className="evidence-link" href={source.url} target="_blank" rel="noreferrer" title={source.url}>
                      <ExternalLink size={13} />
                      <span className="evidence-title">{source.title}</span>
                      <small>{shortUrl(source.url)}</small>
                    </a>
                    <span className="evidence-provider">{source.provider}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      ) : (
        <p className="analysis-placeholder">尚未启动辅助分析。</p>
      )}
      <div className="form-actions"><button className="button primary" type="button" disabled={busy || item.status === "analyzing"} onClick={() => void analyze()}>{busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />} {item.analysis ? "重新分析" : "启动辅助分析"}</button></div>
    </section>
  );
}

export function CaseReviewPage() {
  const { item, setItem } = useCase();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canReview = item.status === "awaiting_review";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const input: ReviewInput = {
      decision: String(data.get("decision")) as ReviewInput["decision"],
      final_impression: String(data.get("final_impression") ?? ""),
      note: String(data.get("note") ?? ""),
      reviewer: String(data.get("reviewer") ?? "医生"),
    };
    setBusy(true);
    setError(null);
    try {
      setItem(await reviewCase(item.id, input));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "复核保存失败");
    } finally {
      setBusy(false);
    }
  }

  if (!canReview && item.review) return <section className="panel"><div className="section-heading"><div><h2>医生复核</h2><span>已于 {new Date(item.review.reviewed_at).toLocaleString("zh-CN")} 完成</span></div><CheckCircle2 size={20} /></div><div className="clinical-text"><span>复核医生</span><p>{item.review.reviewer}</p></div><div className="clinical-text"><span>最终印象</span><p>{item.review.final_impression || "未填写"}</p></div><div className="clinical-text"><span>复核说明</span><p>{item.review.note || "未填写"}</p></div></section>;
  if (!canReview) return <section className="panel"><div className="empty-state"><ShieldCheck size={26} /><p>暂不能复核</p><span>需要先完成辅助分析。</span></div></section>;
  return (
    <form className="panel" onSubmit={(event) => void submit(event)}>
      <div className="section-heading"><div><h2>医生复核</h2><span>保存后作为本病例的最终记录</span></div><ShieldCheck size={20} /></div>
      {error && <div className="notice error-notice">{error}</div>}
      <div className="form-grid">
        <label>复核结论<select name="decision" defaultValue="accepted"><option value="accepted">认可结果</option><option value="modified">修改结论</option><option value="rejected">驳回结果</option></select></label>
        <label>复核医生<input name="reviewer" required defaultValue="医生" maxLength={100} /></label>
        <label className="span-2">最终印象<textarea name="final_impression" maxLength={2000} placeholder="与辅助结果一致时可留空" /></label>
        <label className="span-2">复核说明<textarea name="note" maxLength={4000} placeholder="修改或驳回时必填" /></label>
      </div>
      <div className="form-actions"><button className="button primary" type="submit" disabled={busy}><ShieldCheck size={16} /> 保存复核</button></div>
    </form>
  );
}

export function CaseReportPage() {
  const { item } = useCase();
  return <section className="panel case-report"><div className="section-heading"><div><h2>病例报告</h2><span>仅展示医生确认后的内容</span></div><FileImage size={20} /></div>{item.review ? <><h1>{item.patient_age} 岁 · {sexText[item.patient_sex]} · {eyeText[item.affected_eye]}</h1><p>{item.review.final_impression || "医生未填写最终印象"}</p><small>复核医生：{item.review.reviewer} · {new Date(item.review.reviewed_at).toLocaleString("zh-CN")}</small></> : <div className="empty-state"><ShieldCheck size={26} /><p>报告尚未形成</p><span>完成医生复核后可在此查看。</span></div>}</section>;
}

function useCase() {
  const value = useContext(CaseContext);
  if (!value) throw new Error("Case context missing");
  return value;
}

const analysisText = { queued: "等待处理", running: "处理中", completed: "分析完成", failed: "分析未完成" };
const jobStatusText = { queued: "排队中", running: "分析中", finalizing: "正在写回结果", completed: "分析完成", failed: "分析未完成" };
