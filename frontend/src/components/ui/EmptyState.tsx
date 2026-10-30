import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type EmptyStateProps = {
  title: string;
  description?: ReactNode;
  icon?: LucideIcon;
};

export default function EmptyState({ title, description, icon: Icon }: EmptyStateProps) {
  return (
    <div className="empty-state">
      {Icon ? <Icon size={26} /> : null}
      <p>{title}</p>
      {description ? <span>{description}</span> : null}
    </div>
  );
}
