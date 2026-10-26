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
    <main className="admin-login-page">
      <section className="admin-login-panel">
        <header className="admin-login-header">
          <Link className="login-brand" to="/">
            <span className="brand-mark"><Activity size={20} /></span>
            <span>葡萄膜炎辅助诊断系统</span>
          </Link>
          <span className="admin-login-label"><ShieldCheck size={15} /> 管理控制台</span>
        </header>
        <div className="admin-login-content">
          <div className="login-heading">
            <ShieldCheck size={22} />
            <div><h1>管理员登录</h1><p>仅限系统管理员访问配置、账号权限与审计功能。</p></div>
          </div>
          {error && <div className="notice error-notice" role="alert"><AlertCircle size={17} /> {error}</div>}
          <form className="login-form" onSubmit={(event) => void handleSubmit(event)}>
            <label>管理员账号<input name="username" autoComplete="username" required autoFocus /></label>
            <label>密码<input name="password" type="password" autoComplete="current-password" required /></label>
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}
              进入管理后台
            </button>
          </form>
        </div>
        <footer className="admin-login-footer">
          <Link to="/login">医生入口</Link>
          <Link to="/">患者指南</Link>
        </footer>
      </section>
    </main>
  );
}
