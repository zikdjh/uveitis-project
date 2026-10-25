import {
  AlertTriangle,
  CheckCircle2,
  Clock3,
  FileImage,
  ShieldCheck,
  Stethoscope,
} from "lucide-react";
import { Link } from "react-router-dom";

export default function HomePage() {
  return (
    <section className="page patient-page">
      <section className="patient-intro">
        <div>
          <p className="eyebrow">葡萄膜炎就诊助手</p>
          <h1>眼部不适时，先确认是否需要尽快就医。</h1>
          <p className="patient-lead">
            这里帮助患者整理症状与检查资料，并说明就诊时需要告知医生的信息。线上内容不能代替眼科检查与诊断。
          </p>
          <div className="patient-actions">
            <a className="button primary" href="#urgent-care">
              <AlertTriangle size={16} /> 查看就医提示
            </a>
            <Link className="button secondary" to="/doctor">
              <Stethoscope size={16} /> 医生入口
            </Link>
          </div>
        </div>
        <aside className="patient-callout" id="urgent-care">
          <div className="callout-title">
            <AlertTriangle size={20} />
            <h2>出现这些情况请及时就医</h2>
          </div>
          <ul>
            <li>视力突然下降或视野缺损</li>
            <li>明显眼痛、畏光，或眼红持续加重</li>
            <li>眼前黑影突然增多，伴闪光感</li>
            <li>既往葡萄膜炎复发，或症状持续不缓解</li>
          </ul>
          <p>如症状严重、进展迅速，或伴发热等全身不适，请尽快前往有眼科急诊能力的医疗机构。</p>
        </aside>
      </section>

      <section className="patient-section">
        <div className="section-heading">
          <div>
            <h2>就诊前可以准备什么</h2>
            <span>整理清楚信息，有助于医生更快了解病情。</span>
          </div>
        </div>
        <div className="patient-grid">
          {preparations.map(({ icon: Icon, title, body }) => (
            <article key={title}>
              <Icon size={21} />
              <h3>{title}</h3>
              <p>{body}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="patient-section patient-check">
        <div>
          <h2>就诊时告诉医生</h2>
          <p>主诉、起病时间、患眼、既往病史和相关检查都会影响判断。不要只描述“眼睛不舒服”，尽量说清楚变化和持续时间。</p>
        </div>
        <div className="check-list">
          <div><CheckCircle2 size={17} /><span>症状何时开始，是否反复出现</span></div>
          <div><CheckCircle2 size={17} /><span>是否伴眼痛、畏光、视力变化或黑影</span></div>
          <div><CheckCircle2 size={17} /><span>正在使用的眼药、口服药及过敏史</span></div>
          <div><CheckCircle2 size={17} /><span>既往检查、影像与病历资料</span></div>
        </div>
      </section>

      <div className="patient-disclaimer">
        <ShieldCheck size={17} />
        <span>本页面仅提供就医与资料准备提示，不提供诊断，也不替代眼科医生的面诊判断。</span>
      </div>
    </section>
  );
}

const preparations = [
  {
    icon: Clock3,
    title: "记录症状变化",
    body: "写明起病时间、哪只眼不适，以及视力、疼痛、畏光等症状是否在加重。",
  },
  {
    icon: FileImage,
    title: "带好检查资料",
    body: "整理近期眼底照片、OCT、眼压和血液检查结果；原始影像比手机翻拍更清晰。",
  },
  {
    icon: Stethoscope,
    title: "准备既往病史",
    body: "告知全身疾病、近期感染、用药和过敏情况；女性请说明是否妊娠或备孕。",
  },
];
