// DemoBadge — inline indicator shown when a data source is backed by demo/stub data.
// Uses the existing .badge / .badge-warn CSS classes from App.css.

interface DemoBadgeProps {
  isDemo: boolean;
  label?: string;
}

export function DemoBadge({ isDemo, label = 'DEMO DATA' }: DemoBadgeProps) {
  if (!isDemo) return null;
  return (
    <span className="badge badge-warn" title="This layer is currently backed by demo data, not a live feed">
      {label}
    </span>
  );
}
