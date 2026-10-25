import {
  AlertCircle,
  CheckCircle2,
  ChevronRight,
  ClipboardPlus,
  FileImage,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  Upload,
} from "lucide-react";
import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";

import {
  analyzeCase,
  createCase,
  listCases,
  reviewCase,
  uploadCaseImages,
  type CaseCreateInput,
  type CaseRecord,
  type ImageKind,
  type ReviewInput,
} from "@/api/cases";

const statusText: Record<CaseRecord["status"], string> = {
  created: "待分析",
  analyzing: "分析中",
  awaiting_review: "待复核",
  reviewed: "已复核",
  failed: "分析失败",
};

const emptyForm: CaseCreateInput = {
  patient_age: 40,
  patient_sex: "F",
  complaint: "",
  medical_history: "",
  affected_eye: "UNKNOWN",
  consent_confirmed: false,
};

export default function DoctorPage() {
  const [cases, setCases] = useState<CaseRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState<CaseCreateInput>(emptyForm);
  const [files, setFiles] = useState<File[]>([]);
  const [imageKind, setImageKind] = useState<ImageKind>("fundus");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const selected = cases.find((item) => item.id === selectedId) ?? null;

  async function refresh(preferredId?: string) {
    const result = await listCases();
    setCases(result);
    setSelectedId((current) => preferredId ?? current ?? result[0]?.id ?? null);
  }

  useEffect(() => {
    refresh().catch((reason: unknown) =>
      setError(reason instanceof Error ? reason.message : "病例列表加载失败"),
    );
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const created = await createCase(form);
      let updated = created;
      if (files.length > 0) {
        updated = await uploadCaseImages(created.id, files, imageKind);
      }
      setCases((current) => [updated, ...current]);
      setSelectedId(updated.id);
      setForm(emptyForm);
      setFiles([]);
      setNotice("病例已建档，可以启动辅助分析。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "病例创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleAnalyze() {
    if (!selected) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const queued = await analyzeCase(selected.id);
      replaceCase(queued);
      await waitForAnalysis(selected.id);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "分析任务启动失败");
    } finally {
      setBusy(false);
    }
  }

  async function waitForAnalysis(caseId: string) {
    for (let attempt = 0; attempt < 20; attempt += 1) {
      await new Promise((resolve) => setTimeout(resolve, 700));
      const result = await listCases();
      setCases(result);
      const latest = result.find((item) => item.id === caseId);
      if (latest && latest.status !== "analyzing") {
        setNotice(
          latest.status === "failed"
            ? "分析任务失败，请查看流程记录。"
            : "分析流程已完成，等待医生复核。",
        );
        return;
      }
    }
    setNotice("任务仍在运行，可稍后刷新列表。");
  }

  async function handleReview(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
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
      const reviewed = await reviewCase(selected.id, input);
      replaceCase(reviewed);
      setNotice("复核结果已保存。");
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "复核保存失败");
    } finally {
      setBusy(false);
    }
  }

  function replaceCase(updated: CaseRecord) {
    setCases((current) => current.map((item) => (item.id === updated.id ? updated : item)));
  }

  function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    setFiles(Array.from(event.target.files ?? []));
  }

  return (
    <section className="page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">CLINICAL WORKSPACE</p>
          <h1>医生工作台</h1>
          <p className="page-lead">病例建档、影像整理、辅助分析与人工复核。</p>
        </div>
        <button className="button secondary" type="button" onClick={() => void refresh()} disabled={busy}>
          <RefreshCw size={16} /> 刷新病例
        </button>
      </div>

      {error && (
        <div className="notice error-notice" role="alert">
          <AlertCircle size={17} /> {error}
        </div>
      )}
      {notice && (
        <div className="notice success-notice">
          <CheckCircle2 size={17} /> {notice}
        </div>
      )}

      <div className="workspace-grid">
        <aside className="case-list">
          <div className="section-heading">
            <div>
              <h2>病例队列</h2>
              <span>{cases.length} 份病例</span>
            </div>
          </div>
          {cases.length === 0 ? (
            <div className="empty-state">
              <ClipboardPlus size={26} />
              <p>还没有病例</p>
              <span>从右侧新建第一份病例。</span>
            </div>
          ) : (
            <div className="case-items">
              {cases.map((item) => (
                <button
                  className={`case-item ${item.id === selectedId ? "active" : ""}`}
                  key={item.id}
                  type="button"
                  onClick={() => setSelectedId(item.id)}
                >
                  <div className="case-item-top">
                    <strong>{item.patient_age} 岁 · {sexText[item.patient_sex]}</strong>
                    <span className={`status ${item.status}`}>{statusText[item.status]}</span>
                  </div>
                  <p>{item.complaint}</p>
                  <span className="case-meta">
                    {formatDate(item.updated_at)} · {item.images.length} 张影像
                  </span>
                </button>
              ))}
            </div>
          )}
        </aside>

        <div className="doctor-main">
          <form className="panel" onSubmit={(event) => void handleSubmit(event)}>
            <div className="section-heading">
              <div>
                <h2>新建病例</h2>
                <span>仅用于辅助参考，须获得资料使用授权</span>
              </div>
              <ClipboardPlus size={20} />
            </div>
            <div className="form-grid">
              <label>
                年龄
                <input
                  name="patient_age"
                  type="number"
                  min="0"
                  max="130"
                  required
                  value={form.patient_age}
                  onChange={(event) => setForm({ ...form, patient_age: Number(event.target.value) })}
                />
              </label>
              <label>
                性别
                <select
                  name="patient_sex"
                  value={form.patient_sex}
                  onChange={(event) =>
                    setForm({ ...form, patient_sex: event.target.value as CaseCreateInput["patient_sex"] })
                  }
                >
                  <option value="F">女</option>
                  <option value="M">男</option>
                  <option value="U">未说明</option>
                </select>
              </label>
              <label>
                患眼
                <select
                  name="affected_eye"
                  value={form.affected_eye}
                  onChange={(event) =>
                    setForm({ ...form, affected_eye: event.target.value as CaseCreateInput["affected_eye"] })
                  }
                >
                  <option value="UNKNOWN">未确认</option>
                  <option value="OD">右眼</option>
                  <option value="OS">左眼</option>
                  <option value="OU">双眼</option>
                </select>
              </label>
              <label>
                影像类型
                <select name="image_kind" value={imageKind} onChange={(event) => setImageKind(event.target.value as ImageKind)}>
                  <option value="fundus">眼底</option>
                  <option value="ultrawide">超广角</option>
                  <option value="oct">OCT</option>
                  <option value="anterior">眼前段</option>
                  <option value="other">其他</option>
                </select>
              </label>
              <label className="span-2">
                主诉
                <textarea
                  name="complaint"
                  required
                  minLength={2}
                  maxLength={2000}
                  placeholder="例如：左眼视物模糊伴眼前黑影三天"
                  value={form.complaint}
                  onChange={(event) => setForm({ ...form, complaint: event.target.value })}
                />
              </label>
              <label className="span-2">
                病史与已有检查
                <textarea
                  name="medical_history"
                  maxLength={4000}
                  placeholder="既往史、用药、实验室检查等；不要录入不必要的身份信息"
                  value={form.medical_history}
                  onChange={(event) => setForm({ ...form, medical_history: event.target.value })}
                />
              </label>
              <label className="file-input span-2">
                <Upload size={18} />
                <span>{files.length ? `已选择 ${files.length} 个文件` : "添加影像（PNG / JPEG / TIFF，单张不超过 25 MB）"}</span>
                <input type="file" multiple accept=".png,.jpg,.jpeg,.tif,.tiff" onChange={handleFiles} />
              </label>
              <label className="checkbox-row span-2">
                <input
                  type="checkbox"
                  checked={form.consent_confirmed}
                  onChange={(event) => setForm({ ...form, consent_confirmed: event.target.checked })}
                  required
                />
                <span>我确认已获得病例资料用于辅助分析的必要授权。</span>
              </label>
            </div>
            <div className="form-actions">
              <button className="button primary" type="submit" disabled={busy || !form.consent_confirmed}>
                {busy ? <LoaderCircle className="spin" size={16} /> : <ClipboardPlus size={16} />}
                创建病例
              </button>
            </div>
          </form>

          {selected ? (
            <CaseDetail
              item={selected}
              busy={busy}
              onAnalyze={() => void handleAnalyze()}
              onReview={handleReview}
            />
          ) : (
            <div className="panel placeholder-panel">
              <FileImage size={28} />
              <h2>选择一个病例</h2>
              <p>查看病例资料、辅助结果与复核记录。</p>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function CaseDetail({
  item,
  busy,
  onAnalyze,
  onReview,
}: {
  item: CaseRecord;
  busy: boolean;
  onAnalyze: () => void;
  onReview: (event: FormEvent<HTMLFormElement>) => Promise<void>;
}) {
  const canAnalyze = item.status !== "analyzing";
  const canReview = item.status === "awaiting_review";
  return (
    <>
      <section className="panel">
        <div className="detail-heading">
          <div>
            <div className="detail-title">
              <h2>病例详情</h2>
              <span className={`status ${item.status}`}>{statusText[item.status]}</span>
            </div>
            <p>编号 {item.id.slice(0, 8)} · {formatDate(item.created_at)}</p>
          </div>
          <button className="button primary" type="button" onClick={onAnalyze} disabled={busy || !canAnalyze}>
            {busy ? <LoaderCircle className="spin" size={16} /> : <ChevronRight size={16} />}
            {item.status === "reviewed" ? "重新分析" : "启动辅助分析"}
          </button>
        </div>
        <div className="clinical-facts">
          <div><span>患者</span><strong>{item.patient_age} 岁 · {sexText[item.patient_sex]}</strong></div>
          <div><span>患眼</span><strong>{eyeText[item.affected_eye]}</strong></div>
          <div><span>影像</span><strong>{item.images.length} 张</strong></div>
        </div>
        <div className="clinical-text">
          <span>主诉</span>
          <p>{item.complaint}</p>
        </div>
        <div className="clinical-text">
          <span>病史与检查</span>
          <p>{item.medical_history || "未填写"}</p>
        </div>
        {item.images.length > 0 && (
          <div className="image-list">
            {item.images.map((image) => (
              <a href={image.url} target="_blank" rel="noreferrer" key={image.id}>
                <FileImage size={16} />
                <span>{image.filename}</span>
                <small>{imageKindText[image.kind]} · {formatBytes(image.size_bytes)}</small>
              </a>
            ))}
          </div>
        )}
      </section>

      {item.analysis && (
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>辅助分析结果</h2>
              <span>分析结果须结合临床资料判断</span>
            </div>
            <ShieldCheck size={20} />
          </div>
          <div className="analysis-summary">
            <div><span>状态</span><strong>{analysisStatusText[item.analysis.status]}</strong></div>
            <div><span>完成时间</span><strong>{item.analysis.completed_at ? formatDate(item.analysis.completed_at) : "处理中"}</strong></div>
          </div>
          {item.analysis.impression && (
            <div className="result-box">
              <span>流程结论</span>
              <p>{item.analysis.impression}</p>
              <small>置信度 {Math.round(item.analysis.confidence * 100)}% · 紧急度 {urgencyText[item.analysis.urgency]}</small>
            </div>
          )}
          {item.analysis.recommendations.length > 0 && (
            <div className="result-box">
              <span>下一步建议</span>
              <ul>{item.analysis.recommendations.map((text) => <li key={text}>{text}</li>)}</ul>
            </div>
          )}
          {!item.analysis.impression && !item.analysis.error && (
            <p className="analysis-placeholder">本次未生成临床结论，请结合原始影像和检查资料判断。</p>
          )}
          {item.analysis.error && <div className="notice error-notice">{item.analysis.error}</div>}
        </section>
      )}

      {canReview && (
        <form className="panel" onSubmit={(event) => void onReview(event)}>
          <div className="section-heading">
            <div><h2>医生复核</h2><span>保存后作为本病例的最终记录</span></div>
            <ShieldCheck size={20} />
          </div>
          <div className="form-grid">
            <label>
              复核结论
              <select name="decision" defaultValue="accepted">
                <option value="accepted">认可结果</option>
                <option value="modified">修改结论</option>
                <option value="rejected">驳回结果</option>
              </select>
            </label>
            <label>
              复核医生
              <input name="reviewer" required defaultValue="医生" maxLength={100} />
            </label>
            <label className="span-2">
              最终印象
              <textarea name="final_impression" maxLength={2000} placeholder="与辅助结果一致时可留空" />
            </label>
            <label className="span-2">
              复核说明
              <textarea name="note" maxLength={4000} placeholder="修改或驳回时必填" />
            </label>
          </div>
          <div className="form-actions">
            <button className="button primary" type="submit" disabled={busy}>
              <ShieldCheck size={16} /> 保存复核
            </button>
          </div>
        </form>
      )}
    </>
  );
}

const sexText = { F: "女", M: "男", U: "未说明" };
const eyeText = { OD: "右眼", OS: "左眼", OU: "双眼", UNKNOWN: "未确认" };
const imageKindText = { fundus: "眼底", ultrawide: "超广角", oct: "OCT", anterior: "眼前段", other: "其他" };
const analysisStatusText = { queued: "等待处理", running: "处理中", completed: "分析完成", failed: "分析未完成" };
const urgencyText = { unknown: "待定", low: "低", medium: "中", high: "高" };

function formatDate(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function formatBytes(bytes: number) {
  if (bytes < 1024 * 1024) return `${Math.ceil(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
