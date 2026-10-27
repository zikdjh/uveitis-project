import {
  Activity,
  ClipboardList,
  FileText,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  ScanEye,
  Settings2,
  ShieldCheck,
  Users,
  X,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";

import { getCurrentUser, logout, type User } from "@/api/auth";

type WorkspaceMode = "doctor" | "admin";

type NavItem = {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  end?: boolean;
};

type NavGroup = {
  label: string;
  items: NavItem[];
};

const navigation: Record<WorkspaceMode, NavGroup[]> = {
  doctor: [
    {
      label: "临床工作",
      items: [
        { to: "/doctor/workbench", label: "工作台", icon: LayoutDashboard },
        { to: "/doctor/cases", label: "病例", icon: ClipboardList },
        { to: "/doctor/reviews", label: "待复核", icon: ShieldCheck },
      ],
    },
    {
      label: "资料与账号",
      items: [
        { to: "/doctor/knowledge", label: "临床知识", icon: ScanEye },
        { to: "/doctor/security", label: "账号安全", icon: KeyRound },
      ],
    },
  ],
  admin: [
    {
      label: "运行管理",
      items: [
        { to: "/admin", label: "运行概览", icon: LayoutDashboard, end: true },
        { to: "/admin/cases", label: "病例审计", icon: ClipboardList },
        { to: "/admin/knowledge", label: "知识库", icon: FileText },
        { to: "/admin/services", label: "服务配置", icon: Settings2 },
      ],
    },
    {
      label: "权限与安全",
      items: [
        { to: "/admin/access", label: "医生账号", icon: Users },
        { to: "/admin/security", label: "账号安全", icon: KeyRound },
      ],
    },
  ],
};

function userInitials(user: User | null) {
  if (!user) return "用户";
  const value = user.display_name.trim() || user.username;
  return value.slice(0, 2).toUpperCase();
}

function currentPageLabel(pathname: string, groups: NavGroup[]) {
  const items = groups.flatMap((group) => group.items);
  const matched = items
    .filter((item) => pathname === item.to || pathname.startsWith(`${item.to}/`))
    .sort((left, right) => right.to.length - left.to.length)[0];
  return matched?.label ?? "工作区";
}

export default function WorkspaceShell({ mode }: { mode: WorkspaceMode }) {
  const navigate = useNavigate();
  const location = useLocation();
  const loginPath = mode === "admin" ? "/admin/login" : "/login";
  const groups = navigation[mode];
  const [mobileOpen, setMobileOpen] = useState(false);
  const [user, setUser] = useState<User | null>(null);
  const pageLabel = useMemo(
    () => currentPageLabel(location.pathname, groups),
    [groups, location.pathname],
  );

  useEffect(() => {
    getCurrentUser().then(setUser).catch(() => undefined);
    function handleUnauthorized() {
      navigate(loginPath, { replace: true });
    }
    window.addEventListener("auth:unauthorized", handleUnauthorized);
    return () => window.removeEventListener("auth:unauthorized", handleUnauthorized);
  }, [loginPath, navigate]);

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  async function handleLogout() {
    await logout().catch(() => undefined);
    navigate(loginPath, { replace: true });
  }

  return (
    <div className={`app-shell${mobileOpen ? " nav-open" : ""}`}>
      <aside
        id="workspace-navigation"
        className={`sidebar${mobileOpen ? " open" : ""}`}
        aria-label={mode === "doctor" ? "医生工作区导航" : "系统管理导航"}
      >
        <div className="sidebar-brand-row">
          <Link className="brand" to={mode === "doctor" ? "/doctor/workbench" : "/admin"}>
            <span className="brand-mark"><Activity size={20} /></span>
            <span>
              <strong>{mode === "doctor" ? "医生工作台" : "运行管理"}</strong>
              <small>葡萄膜炎辅助记录</small>
            </span>
          </Link>
          <button
            className="sidebar-close"
            type="button"
            onClick={() => setMobileOpen(false)}
            aria-label="关闭导航"
          >
            <X size={19} />
          </button>
        </div>

        <div className="sidebar-context">
          <span className="context-dot" />
          <span>{mode === "doctor" ? "临床工作区" : "运行控制台"}</span>
        </div>

        <nav className="app-nav">
          {groups.map((group) => (
            <div className="nav-group" key={group.label}>
              <span className="nav-label">{group.label}</span>
              {group.items.map(({ to, label, icon: Icon, end }) => (
                <NavLink to={to} end={end ?? false} key={to} title={label}>
                  <Icon size={18} />
                  <span>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="sidebar-actions">
          <div className="sidebar-user">
            <span className="user-avatar">{userInitials(user)}</span>
            <span className="user-copy">
              <strong>{user?.display_name ?? "正在读取"}</strong>
              <small>{user ? (user.role === "admin" ? "系统管理员" : "医生") : "账号信息"}</small>
            </span>
          </div>
          <button className="sidebar-logout" type="button" onClick={() => void handleLogout()}>
            <LogOut size={16} />
            <span>退出登录</span>
          </button>
        </div>
      </aside>

      <button
        className="mobile-backdrop"
        type="button"
        onClick={() => setMobileOpen(false)}
        aria-label="关闭导航"
      />

      <div className="app-content">
        <header className="mobile-header">
          <button
            className="mobile-menu-button"
            type="button"
            aria-controls="workspace-navigation"
            aria-expanded={mobileOpen}
            onClick={() => setMobileOpen(true)}
          >
            <Menu size={20} />
          </button>
          <div className="mobile-page-title">
            <span>{mode === "doctor" ? "医生工作台" : "运行管理"}</span>
            <strong>{pageLabel}</strong>
          </div>
          <button
            className="mobile-user-button"
            type="button"
            onClick={() => void handleLogout()}
            aria-label="退出登录"
          >
            <span>{userInitials(user)}</span>
            <LogOut size={16} />
          </button>
        </header>

        <main className="app-main"><Outlet /></main>
      </div>
    </div>
  );
}
