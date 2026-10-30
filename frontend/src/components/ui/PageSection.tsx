import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type PageSectionProps = {
  title?: string;
  description?: ReactNode;
  icon?: LucideIcon;
  actions?: ReactNode;
  footer?: ReactNode;
  className?: string;
  children: ReactNode;
};

export default function PageSection({
  title,
  description,
  icon: Icon,
  actions,
  footer,
  className = "",
  children,
}: PageSectionProps) {
  const hasHeading = Boolean(title || description || actions || Icon);

  return (
    <section className={`panel ${className}`.trim()}>
      {hasHeading ? (
        <div className="section-heading">
          <div>
            {title ? <h2>{title}</h2> : null}
            {description ? <span>{description}</span> : null}
          </div>
          {actions ?? (Icon ? <Icon size={20} /> : null)}
        </div>
      ) : null}
      <div className="panel-body">{children}</div>
      {footer ? <div className="panel-footer">{footer}</div> : null}
    </section>
  );
}
