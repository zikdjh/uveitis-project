import { AlertCircle, Activity, ArrowRight, LoaderCircle, LockKeyhole } from "lucide-react";
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
      const { user } = await login({
        username: String(form.get("username") ?? ""),
        password: String(form.get("password") ?? ""),
      });
      const from = (location.state as { from?: string } | null)?.from;
      navigate(from || (user.role === "admin" ? "/admin" : "/doctor/workbench"), {
        replace: true,
      });
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败，请稍后重试");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-page">
      <section className="login-card">
        <Link className="login-brand" to="/">
          <span className="brand-mark"><Activity size={20} /></span>
          <span>葡萄膜炎就诊助手</span>
        </Link>
        <div className="login-heading">
          <LockKeyhole size={21} />
          <div><h1>医务人员登录</h1><p>病例资料仅对授权医生与管理员开放。</p></div>
        </div>
        {error && <div className="notice error-notice" role="alert"><AlertCircle size={17} /> {error}</div>}
        <form className="login-form" onSubmit={(event) => void handleSubmit(event)}>
          <label>账号<input name="username" autoComplete="username" required autoFocus /></label>
          <label>密码<input name="password" type="password" autoComplete="current-password" required /></label>
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? <LoaderCircle className="spin" size={16} /> : <ArrowRight size={16} />}
            登录
          </button>
        </form>
        <Link className="login-back" to="/">返回患者指南</Link>
      </section>
    </main>
  );
}
