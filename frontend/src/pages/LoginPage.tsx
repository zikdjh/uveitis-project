import { Activity, AlertCircle, ArrowRight, LoaderCircle, LockKeyhole } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { login } from "@/api/auth";

export default function LoginPage() {
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
      await login({
        username: String(form.get("username") ?? ""),
        password: String(form.get("password") ?? ""),
      });
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from?.startsWith("/doctor") ? from : "/doctor/workbench", {
        replace: true,
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败，请稍后重试");
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
            <span>葡萄膜炎就诊助手</span>
          </Link>
          <span className="auth-mode-badge"><LockKeyhole size={14} /> 医生工作台</span>
        </header>
        <div className="auth-content">
          <div className="auth-heading">
            <span className="auth-heading-icon"><LockKeyhole size={20} /></span>
            <div>
              <p className="eyebrow">授权访问</p>
              <h1>医生登录</h1>
              <p>病例资料仅对授权医生开放，登录后仅可访问本人负责的病例。</p>
            </div>
          </div>
          {error && <div className="notice error-notice" role="alert"><AlertCircle size={17} /> {error}</div>}
          <form className="login-form auth-form" onSubmit={(event) => void handleSubmit(event)}>
            <label><span>账号</span><input name="username" autoComplete="username" placeholder="请输入医生账号" required autoFocus /></label>
            <label><span>密码</span><input name="password" type="password" autoComplete="current-password" placeholder="请输入登录密码" required /></label>
            <button className="button primary" type="submit" disabled={busy}>
              {busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}
              登录
            </button>
          </form>
        </div>
        <footer className="auth-footer">
          <Link to="/admin/login">管理员入口</Link>
          <Link to="/">患者指南</Link>
        </footer>
      </section>
    </main>
  );
}
