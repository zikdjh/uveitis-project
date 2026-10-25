import { ArrowLeft, ShieldAlert } from "lucide-react";
import { Link } from "react-router-dom";

export function ForbiddenPage() {
  return (
    <main className="status-page">
      <div>
        <ShieldAlert size={30} />
        <h1>无法访问此页面</h1>
        <p>当前账号没有所需权限。</p>
        <Link className="button secondary" to="/"><ArrowLeft size={16} /> 返回患者指南</Link>
      </div>
    </main>
  );
}

export function NotFoundPage() {
  return (
    <main className="status-page">
      <div>
        <h1>页面不存在</h1>
        <p>链接可能已经失效，或地址输入有误。</p>
        <Link className="button secondary" to="/"><ArrowLeft size={16} /> 返回患者指南</Link>
      </div>
    </main>
  );
}
