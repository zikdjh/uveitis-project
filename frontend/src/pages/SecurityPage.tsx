import {
  AlertCircle,
  CheckCircle2,
  KeyRound,
  LoaderCircle,
  MonitorSmartphone,
  RefreshCw,
  ShieldCheck,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";

import {
  changePassword,
  getCurrentUser,
  listSessions,
  revokeOtherSessions,
  revokeSession,
  type Session,
  type User,
} from "@/api/auth";

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

export default function SecurityPage() {
  const [user, setUser] = useState<User | null>(null);
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [currentUser, sessionList] = await Promise.all([
        getCurrentUser(),
        listSessions(),
      ]);
      setUser(currentUser);
      setSessions(sessionList);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "账号信息加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handlePassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const newPassword = String(form.get("new_password") ?? "");
    if (newPassword !== String(form.get("confirm_password") ?? "")) {
      setError("两次输入的新密码不一致");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await changePassword({
        current_password: String(form.get("current_password") ?? ""),
        new_password: newPassword,
      });
      formElement.reset();
      setNotice("密码已更新，其他设备上的会话已撤销。");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "密码更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(sessionId: string) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await revokeSession(sessionId);
      setNotice("会话已撤销。");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "会话撤销失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleRevokeOthers() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await revokeOtherSessions();
      setNotice("其他设备上的会话已全部撤销。");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "会话撤销失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <div className="page-heading">
        <div><h1>账号安全</h1><p className="page-lead">维护当前账号密码与登录会话。</p></div>
        <button className="button secondary" type="button" onClick={() => void load()} disabled={loading || busy}>
          <RefreshCw size={16} className={loading ? "spin" : ""} /> 刷新
        </button>
      </div>
      {error && <div className="notice error-notice" role="alert"><AlertCircle size={17} /> {error}</div>}
      {notice && <div className="notice success-notice"><CheckCircle2 size={17} /> {notice}</div>}

      <div className="security-grid">
        <section className="panel">
          <div className="section-heading">
            <div><h2>账号信息</h2><span>当前登录身份</span></div>
            <ShieldCheck size={20} />
          </div>
          {user ? (
            <dl className="account-facts">
              <div><dt>姓名</dt><dd>{user.display_name}</dd></div>
              <div><dt>账号</dt><dd>{user.username}</dd></div>
              <div><dt>角色</dt><dd>{user.role === "admin" ? "系统管理员" : "医生"}</dd></div>
              <div><dt>状态</dt><dd>{user.is_active ? "启用" : "停用"}</dd></div>
            </dl>
          ) : (
            <div className="loading-panel"><LoaderCircle className="spin" size={22} /> 正在读取账号</div>
          )}
        </section>

        <section className="panel">
          <div className="section-heading">
            <div><h2>修改密码</h2><span>更新后撤销其他会话</span></div>
            <KeyRound size={20} />
          </div>
          <form className="form-grid compact" onSubmit={(event) => void handlePassword(event)}>
            <label className="span-2">当前密码<input name="current_password" type="password" autoComplete="current-password" required /></label>
            <label>新密码<input name="new_password" type="password" minLength={12} maxLength={200} autoComplete="new-password" required /></label>
            <label>确认新密码<input name="confirm_password" type="password" minLength={12} maxLength={200} autoComplete="new-password" required /></label>
            <div className="form-actions span-2">
              <button className="button primary" type="submit" disabled={busy}>
                {busy ? <LoaderCircle className="spin" size={16} /> : <KeyRound size={16} />} 更新密码
              </button>
            </div>
          </form>
        </section>
      </div>

      <section className="panel session-panel">
        <div className="section-heading">
          <div><h2>登录会话</h2><span>共 {sessions.length} 个有效会话</span></div>
          <button className="button secondary" type="button" onClick={() => void handleRevokeOthers()} disabled={busy || sessions.length <= 1}>
            <MonitorSmartphone size={16} /> 撤销其他会话
          </button>
        </div>
        <div className="session-list">
          {sessions.map((session) => (
            <div className="session-row" key={session.id}>
              <div className="session-icon"><MonitorSmartphone size={17} /></div>
              <div>
                <strong>{session.current ? "当前设备" : "其他设备"}</strong>
                <span>{session.user_agent || "未知客户端"}</span>
                <small>{session.ip_address || "未记录 IP"} · 最近活动 {dateFormatter.format(new Date(session.last_seen_at))}</small>
              </div>
              {!session.current && (
                <button className="text-button danger" type="button" disabled={busy} onClick={() => void handleRevoke(session.id)}>
                  撤销
                </button>
              )}
            </div>
          ))}
        </div>
      </section>
    </section>
  );
}
