import {
  AlertCircle,
  CheckCircle2,
  History,
  KeyRound,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  UserPlus,
  UserX,
  Users,
} from "lucide-react";
import { Button, DatePicker, Input, Pagination, Select } from "antd";
import dayjs, { type Dayjs } from "dayjs";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";

import {
  createUser,
  getCurrentUser,
  listAuthAuditEvents,
  listUsers,
  resetUserPassword,
  updateUser,
  type AuthAuditEvent,
  type User,
} from "@/api/auth";

const dateFormatter = new Intl.DateTimeFormat("zh-CN", {
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
});

const eventLabels: Record<string, string> = {
  login: "登录",
  doctor_login: "医生登录",
  admin_login: "管理员登录",
  token_refresh: "令牌刷新",
  logout: "退出",
  session_revoke: "撤销会话",
  session_revoke_others: "撤销其他会话",
  password_change: "修改密码",
  password_reset: "重置密码",
  user_create: "创建账号",
  user_update: "更新账号",
};

export default function AccessPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [users, setUsers] = useState<User[]>([]);
  const [events, setEvents] = useState<AuthAuditEvent[]>([]);
  const [eventTotal, setEventTotal] = useState(0);
  const [auditLoading, setAuditLoading] = useState(true);
  const [auditPage, setAuditPage] = useState(1);
  const [auditPageSize, setAuditPageSize] = useState(20);
  const auditRequestRef = useRef(0);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [resettingUser, setResettingUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const activeUsers = users.filter((user) => user.is_active).length;
  const adminUsers = users.filter((user) => user.role === "admin").length;
  const inactiveUsers = users.length - activeUsers;
  const selectedEvent = searchParams.get("event") ?? "all";
  const selectedOutcome = searchParams.get("outcome") ?? "all";
  const auditSearch = searchParams.get("search") ?? "";
  const from = validDate(searchParams.get("from"));
  const to = validDate(searchParams.get("to"));
  const auditDateRange: [Dayjs, Dayjs] | null = from && to ? [dayjs(from), dayjs(to)] : null;
  const hasAuditFilters = selectedEvent !== "all" || selectedOutcome !== "all" || Boolean(auditSearch || from || to);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [userList, me] = await Promise.all([
        listUsers(),
        getCurrentUser(),
      ]);
      setUsers(userList);
      setCurrentUser(me);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "权限数据加载失败");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const requestId = ++auditRequestRef.current;
    setAuditLoading(true);
    setError(null);
    listAuthAuditEvents({
      page: auditPage,
      page_size: auditPageSize,
      event: selectedEvent === "all" ? undefined : selectedEvent,
      outcome: selectedOutcome === "all" ? undefined : selectedOutcome,
      from,
      to,
      search: auditSearch,
    })
      .then((result) => {
        if (requestId !== auditRequestRef.current) return;
        setEvents(result.items);
        setEventTotal(result.total);
      })
      .catch((reason: unknown) => {
        if (requestId !== auditRequestRef.current) return;
        setError(reason instanceof Error ? reason.message : "鉴权审计加载失败");
      })
      .finally(() => {
        if (requestId === auditRequestRef.current) setAuditLoading(false);
      });
  }, [auditPage, auditPageSize, auditSearch, from, selectedEvent, selectedOutcome, to]);

  useEffect(() => {
    const pageCount = Math.max(1, Math.ceil(eventTotal / auditPageSize));
    setAuditPage((current) => Math.min(current, pageCount));
  }, [auditPageSize, eventTotal]);

  function updateAuditFilters(next: Partial<Record<"event" | "outcome" | "from" | "to" | "search", string>>) {
    const params = new URLSearchParams(searchParams);
    Object.entries(next).forEach(([key, value]) => {
      if (!value || value === "all") params.delete(key);
      else params.set(key, value);
    });
    setSearchParams(params, { replace: true });
    setAuditPage(1);
  }

  async function handleCreate(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await createUser({
        username: String(form.get("username") ?? ""),
        display_name: String(form.get("display_name") ?? ""),
        password: String(form.get("password") ?? ""),
      });
      formElement.reset();
      setNotice("账号已创建。");
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "账号创建失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleUpdate(user: User, values: Partial<Pick<User, "is_active">>) {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await updateUser(user.id, values);
      setNotice(`${user.display_name} 的权限已更新。`);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "账号更新失败");
    } finally {
      setBusy(false);
    }
  }

  async function handleResetPassword(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!resettingUser) return;
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const password = String(form.get("password") ?? "");
    if (password !== String(form.get("confirm_password") ?? "")) {
      setError("两次输入的密码不一致");
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await resetUserPassword(resettingUser.id, password);
      setNotice(`${resettingUser.display_name} 的密码已重置，原有会话已撤销。`);
      setResettingUser(null);
      await load();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "密码重置失败");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="page">
      <div className="page-heading">
        <div><h1>医生账号管理</h1><p className="page-lead">唯一管理员 root 维护医生账号，系统不提供自助注册。</p></div>
        <button className="button secondary" type="button" onClick={() => void load()} disabled={loading || busy}>
          <RefreshCw size={16} className={loading ? "spin" : ""} /> 刷新
        </button>
      </div>
      {error && <div className="notice error-notice" role="alert"><AlertCircle size={17} /> {error}</div>}
      {notice && <div className="notice success-notice"><CheckCircle2 size={17} /> {notice}</div>}

      <div className="metric-grid access-metric-grid">
        <AccessMetric icon={Users} label="有效账号" value={activeUsers} note="当前可登录" />
        <AccessMetric icon={ShieldCheck} label="唯一管理员" value={adminUsers} note="固定 root 账号" />
        <AccessMetric icon={UserX} label="已停用" value={inactiveUsers} note="不可登录" />
        <AccessMetric icon={History} label="审计事件" value={eventTotal} note="当前筛选总量" />
      </div>

      <div className="access-layout">
        <section className="panel">
          <div className="section-heading">
            <div><h2>账号列表</h2><span>{users.length} 个账号，仅管理员可维护医生账号</span></div>
            <Users size={20} />
          </div>
          {loading && !users.length ? (
            <div className="loading-panel"><LoaderCircle className="spin" size={22} /> 正在读取账号</div>
          ) : (
            <div className="data-table-wrap">
              <table className="data-table">
                <thead><tr><th>人员</th><th>角色</th><th>状态</th><th>操作</th></tr></thead>
                <tbody>
                  {users.map((user) => (
                    <tr key={user.id}>
                      <td data-label="人员">
                        <div className="user-identity">
                          <span className="table-avatar">{initials(user)}</span>
                          <span><strong>{user.display_name}</strong><small>@{user.username}</small></span>
                        </div>
                      </td>
                      <td data-label="角色">{user.is_root ? "唯一管理员" : "医生"}</td>
                      <td data-label="状态">
                        <button
                          className={`status-toggle ${user.is_active ? "active" : "disabled"}`}
                          type="button"
                          disabled={busy || user.id === currentUser?.id || user.is_root}
                          onClick={() => void handleUpdate(user, { is_active: !user.is_active })}
                        >
                          {user.is_active ? "启用" : "停用"}
                        </button>
                      </td>
                      <td data-label="操作">{user.is_root ? <span className="muted">系统固定</span> : <button className="text-button" type="button" onClick={() => setResettingUser(user)}><KeyRound size={14} /> 重置密码</button>}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {!users.length && <div className="empty-state"><Users size={26} /><p>暂无账号</p><span>创建医生账号后可在这里维护。</span></div>}
            </div>
          )}
        </section>

        <section className="panel">
          <div className="section-heading">
            <div><h2>新建医生账号</h2><span>由管理员设置初始密码，密码至少 12 位</span></div>
            <UserPlus size={20} />
          </div>
          <form className="form-grid compact" onSubmit={(event) => void handleCreate(event)}>
            <label>姓名<input name="display_name" required maxLength={100} /></label>
            <label>登录账号<input name="username" required minLength={3} maxLength={100} pattern="[A-Za-z0-9._-]+" /></label>
            <label>初始密码<input name="password" type="password" required minLength={12} maxLength={200} autoComplete="new-password" /></label>
            <div className="form-actions span-2"><button className="button primary" type="submit" disabled={busy}><UserPlus size={16} /> 创建医生账号</button></div>
          </form>
        </section>
      </div>

      {resettingUser && (
        <section className="panel reset-panel">
          <div className="section-heading">
            <div><h2>重置密码</h2><span>{resettingUser.display_name} · {resettingUser.username}</span></div>
            <KeyRound size={20} />
          </div>
          <form className="inline-form" onSubmit={(event) => void handleResetPassword(event)}>
            <label>新密码<input name="password" type="password" required minLength={12} maxLength={200} autoComplete="new-password" /></label>
            <label>确认密码<input name="confirm_password" type="password" required minLength={12} maxLength={200} autoComplete="new-password" /></label>
            <button className="button primary" type="submit" disabled={busy}>确认重置</button>
            <button className="button secondary" type="button" onClick={() => setResettingUser(null)}>取消</button>
          </form>
        </section>
      )}

      <section className="panel audit-panel">
        <div className="section-heading">
          <div><h2>鉴权审计</h2><span>最近的登录、账号与会话操作</span></div>
          <History size={20} />
        </div>
        <div className="audit-filters">
          <Select
            value={selectedEvent}
            onChange={(value) => updateAuditFilters({ event: value })}
            options={[
              { value: "all", label: "全部事件" },
              ...Object.entries(eventLabels).map(([value, label]) => ({ value, label })),
            ]}
            aria-label="按审计事件筛选"
          />
          <Select
            value={selectedOutcome}
            onChange={(value) => updateAuditFilters({ outcome: value })}
            options={[
              { value: "all", label: "全部结果" },
              { value: "success", label: "成功" },
              { value: "failed", label: "失败" },
              { value: "blocked", label: "阻止" },
            ]}
            aria-label="按审计结果筛选"
          />
          <DatePicker.RangePicker
            classNames={{ popup: { root: "case-date-range-popup" } }}
            value={auditDateRange}
            onChange={(dates) => {
              const [start, end] = dates ?? [null, null];
              updateAuditFilters({
                from: start?.format("YYYY-MM-DD") ?? "",
                to: end?.format("YYYY-MM-DD") ?? "",
              });
            }}
            allowClear
            placeholder={["开始日期", "结束日期"]}
            aria-label="按审计时间筛选"
          />
          <Input.Search
            defaultValue={auditSearch}
            key={auditSearch}
            placeholder="账号或说明"
            allowClear
            onSearch={(value) => updateAuditFilters({ search: value.trim() })}
            aria-label="搜索审计账号或说明"
          />
          {hasAuditFilters && (
            <Button onClick={() => updateAuditFilters({ event: "", outcome: "", from: "", to: "", search: "" })}>
              重置
            </Button>
          )}
        </div>
        <div className="audit-list">
          {events.map((event) => (
            <div className="audit-row" key={event.id}>
              <span className={`audit-outcome ${event.outcome}`}>{event.outcome === "success" ? "成功" : event.outcome === "blocked" ? "阻止" : "失败"}</span>
              <div><strong>{eventLabels[event.event] ?? event.event}</strong><span>{event.username} · {event.detail || "无补充信息"}</span></div>
              <time dateTime={event.created_at}>{dateFormatter.format(new Date(event.created_at))}</time>
            </div>
          ))}
          {!auditLoading && !events.length && <div className="empty-state"><History size={26} /><p>{hasAuditFilters ? "没有符合条件的审计记录" : "暂无审计记录"}</p><span>{hasAuditFilters ? "请调整筛选条件。" : "登录与会话操作会显示在这里。"}</span></div>}
        </div>
        {eventTotal > 0 && (
          <Pagination
            className="case-list-pagination"
            current={auditPage}
            pageSize={auditPageSize}
            total={eventTotal}
            showSizeChanger
            pageSizeOptions={[20, 40, 80]}
            showTotal={(total) => `共 ${total} 条`}
            onChange={(page, pageSize) => {
              const changed = pageSize !== auditPageSize;
              setAuditPageSize(pageSize);
              setAuditPage(changed ? 1 : page);
            }}
          />
        )}
      </section>

    </section>
  );
}

function validDate(value: string | null) {
  return value && /^\d{4}-\d{2}-\d{2}$/.test(value) && dayjs(value).isValid() ? value : "";
}

function AccessMetric({ icon: Icon, label, value, note }: { icon: typeof Users; label: string; value: number; note: string }) {
  return (
    <div className="metric-card access-metric">
      <div className="metric-icon"><Icon size={18} /></div>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function initials(user: User) {
  return (user.display_name.trim() || user.username).slice(0, 2).toUpperCase();
}
