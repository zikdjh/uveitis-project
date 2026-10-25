import {
  Activity,
  ClipboardList,
  FileText,
  LayoutDashboard,
  LogOut,
  ScanEye,
  ShieldCheck,
} from "lucide-react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";

import { logout } from "@/api/auth";

const doctorLinks = [
  { to: "/doctor/workbench", label: "工作台", icon: LayoutDashboard },
  { to: "/doctor/cases", label: "病例", icon: ClipboardList },
  { to: "/doctor/reviews", label: "待复核", icon: ShieldCheck },
  { to: "/doctor/knowledge", label: "临床知识", icon: ScanEye },
];

const adminLinks = [
  { to: "/admin", label: "运行概览", icon: LayoutDashboard },
  { to: "/admin/cases", label: "病例审计", icon: ClipboardList },
  { to: "/admin/knowledge", label: "知识库", icon: FileText },
  { to: "/admin/services", label: "服务状态", icon: Activity },
];

export default function WorkspaceShell({ mode }: { mode: "doctor" | "admin" }) {
  const navigate = useNavigate();
  const links = mode === "doctor" ? doctorLinks : adminLinks;

  async function handleLogout() {
    await logout().catch(() => undefined);
    navigate("/login", { replace: true });
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to={mode === "doctor" ? "/doctor/workbench" : "/admin"}>
          <span className="brand-mark"><Activity size={20} /></span>
          <span>
            <strong>{mode === "doctor" ? "医生工作台" : "运行管理"}</strong>
            <small>葡萄膜炎辅助记录</small>
          </span>
        </Link>
        <nav className="app-nav" aria-label={mode === "doctor" ? "医生导航" : "管理导航"}>
          {links.map(({ to, label, icon: Icon }) => (
            <NavLink to={to} end={to === "/admin"} key={to}>
              <Icon size={18} /><span>{label}</span>
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-actions">
          <button type="button" onClick={() => void handleLogout()}>
            <LogOut size={16} /> 退出登录
          </button>
        </div>
        <div className="sidebar-foot"><ShieldCheck size={14} /><span>医疗结论由医生复核</span></div>
      </aside>
      <div className="app-content"><main className="app-main"><Outlet /></main></div>
    </div>
  );
}
