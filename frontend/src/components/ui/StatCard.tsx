import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

type StatCardProps = {
  label: string;
  value: ReactNode;
  note?: string;
  icon?: LucideIcon;
};

export default function StatCard({ label, value, note, icon: Icon }: StatCardProps) {
  return (
    <div className="metric-card">
      {Icon ? (
        <div className="metric-icon">
          <Icon size={18} />
        </div>
      ) : null}
      <span>{label}</span>
      <strong>{value}</strong>
      {note ? <small>{note}</small> : null}
    </div>
  );
}
