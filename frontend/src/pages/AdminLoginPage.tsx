import { Activity, AlertCircle, ArrowRight, LoaderCircle, ShieldCheck } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { adminLogin } from "@/api/auth";

export default function AdminLoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await adminLogin({
        username: String(form.get("username") ?? ""),
        password: String(form.get("password") ?? ""),
      });
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from?.startsWith("/admin") ? from : "/admin", { replace: true });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "管理员登录失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-shell">
        <header className="auth-header">
          <Link className="login-brand" to="/">
            <span className="brand-mark"><Activity size={20} /></span>
            <span>葡萄膜炎辅助诊断系统</span>
          </Link>
          <span className="auth-mode-badge"><ShieldCheck size={14} /> 管理控制台</span>
        </header>
        <div className="auth-content">
          <div className="auth-heading">
            <span className="auth-heading-icon"><ShieldCheck size={20} /></span>
            <div>
              <p className="eyebrow">管理员专用入口</p>
              <h1>管理员登录</h1>
              <p>仅限系统管理员访问配置、账号权限与审计功能。</p>
            </div>
          </div>
          {error && <div className="notice error-notice" role="alert"><AlertCircle size={17} /> {error}</div>}
          <form className="login-form auth-form" onSubmit={(event) => void handleSubmit(event)}>
            <label><span>管理员账号</span><input name="username" autoComplete="username" defaultValue="root" readOnly required autoFocus /></label>
            <label><span>密码</span><input name="password" type="password" autoComplete="current-password" placeholder="请输入管理员密码" required /></label>
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}
              进入管理后台
            </button>
          </form>
        </div>
        <footer className="auth-footer">
          <Link to="/login">医生入口</Link>
          <Link to="/">患者指南</Link>
        </footer>
      </section>
    </main>
  );
}
