import type { ReactNode } from "react";

type PageHeaderProps = {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
};

export default function PageHeader({ title, description, actions }: PageHeaderProps) {
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        {description ? <p className="page-lead">{description}</p> : null}
      </div>
      {actions ? <div className="page-heading-actions">{actions}</div> : null}
    </header>
  );
}
