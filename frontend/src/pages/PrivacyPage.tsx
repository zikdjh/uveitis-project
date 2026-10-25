import { LockKeyhole, ShieldCheck } from "lucide-react";

export default function PrivacyPage() {
  return (
    <section className="page patient-page">
      <div className="page-heading">
        <div>
          <p className="eyebrow">隐私与资料使用</p>
          <h1>您的资料如何被使用</h1>
          <p className="page-lead">患者指南不要求填写病例资料。病例资料只在获得授权后，由医生在受限工作台中使用。</p>
        </div>
      </div>
      <section className="privacy-stack">
        <article><LockKeyhole size={21} /><div><h2>最小必要</h2><p>医生仅录入辅助判断所需的临床信息，避免不必要的患者身份信息。</p></div></article>
        <article><ShieldCheck size={21} /><div><h2>授权后再使用</h2><p>病例建档前需确认已获得资料使用授权；未完成授权不能保存病例。</p></div></article>
        <article><ShieldCheck size={21} /><div><h2>医生复核后发布</h2><p>患者可见的报告只包含医生确认后的内容，不公开原始内部记录或模型流程。</p></div></article>
      </section>
    </section>
  );
}
