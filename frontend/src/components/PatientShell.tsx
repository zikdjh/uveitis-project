import { Activity, HeartHandshake, ShieldCheck } from "lucide-react";
import { Link, Outlet } from "react-router-dom";

export default function PatientShell() {
  return (
    <div className="patient-shell">
      <header className="patient-header">
        <Link className="patient-brand" to="/">
          <span className="brand-mark"><Activity size={19} /></span>
          <span><strong>葡萄膜炎就诊助手</strong><small>患者资料准备与就医提示</small></span>
        </Link>
        <nav className="patient-nav" aria-label="患者导航">
          <Link to="/"><HeartHandshake size={16} /> 就医指南</Link>
          <Link to="/privacy"><ShieldCheck size={16} /> 隐私说明</Link>
          <Link className="patient-login" to="/login">医务人员登录</Link>
        </nav>
      </header>
      <main className="patient-main"><Outlet /></main>
      <footer className="patient-footer">
        线上内容不能替代面诊或眼科检查。医疗结论须由有资质医生复核。
      </footer>
    </div>
  );
}
