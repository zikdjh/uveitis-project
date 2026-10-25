import {
  Activity,
  ClipboardList,
  Stethoscope,
  UserRound,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

const links = [
  { to: "/", label: "患者指南", icon: UserRound, end: true },
  { to: "/doctor", label: "医生工作台", icon: Stethoscope },
];

export default function Shell() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <NavLink className="brand" to="/">
          <span className="brand-mark"><Activity size={20} /></span>
          <span>
            <strong>葡萄膜炎就诊助手</strong>
            <small>患者资料准备与医生工作台</small>
          </span>
        </NavLink>
        <nav className="app-nav" aria-label="主导航">
          {links.map(({ to, label, icon: Icon, end }) => (
            <NavLink to={to} end={end} key={to}>
              <Icon size={18} />
              <span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-foot">
          <ClipboardList size={14} />
          <span>医疗结论由医生复核</span>
        </div>
      </aside>
      <div className="app-content">
        <header className="mobile-header">
          <span className="brand-mark"><Activity size={18} /></span>
          <strong>Uveitis Aid</strong>
        </header>
        <main className="app-main">
          <Outlet />
        </main>
        <footer className="app-footer">
          线上内容不能替代面诊或眼科检查。所有医疗结论须由有资质医生复核。
        </footer>
      </div>
    </div>
  );
}
