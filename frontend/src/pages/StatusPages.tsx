import { Activity, ArrowLeft, FileQuestion, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

export function ForbiddenPage() {
  return (
    <StatusPageLayout
      icon={<ShieldAlert size={27} />}
      title="无法访问此页面"
      description="当前账号没有所需权限，请返回上一页或使用对应角色入口登录。"
    />
  );
}

export function NotFoundPage() {
  return (
    <StatusPageLayout
      icon={<FileQuestion size={27} />}
      title="页面不存在"
      description="链接可能已经失效，或地址输入有误。"
    />
  );
}

function StatusPageLayout({ icon, title, description }: { icon: React.ReactNode; title: string; description: string }) {
  return (
    <main className="auth-page status-page">
      <section className="auth-shell status-shell">
        <header className="auth-header">
          <Link className="login-brand" to="/">
            <span className="brand-mark"><Activity size={20} /></span>
            <span>葡萄膜炎辅助诊断系统</span>
          </Link>
          <span className="auth-mode-badge">状态提示</span>
        </header>
        <div className="auth-content status-content">
          <span className="status-symbol">{icon}</span>
          <h1>{title}</h1>
          <p>{description}</p>
          <div className="status-actions">
            <Link className="button primary" to="/"><ArrowLeft size={16} /> 返回患者指南</Link>
            <Link className="button secondary" to="/login">医生登录</Link>
          </div>
        </div>
      </section>
    </main>
  );
}
