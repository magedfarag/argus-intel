// P2-3.2: Before/after imagery metadata side-by-side compare panel
import { useState } from "react";
import type { ImageryItem } from "../../api/types";

interface Props {
  items: ImageryItem[];
}

function ItemCard({ item, role }: { item: ImageryItem; role: "before" | "after" }) {
  const acqDate = new Date(item.datetime).toLocaleDateString(undefined, {
    year: "numeric", month: "short", day: "numeric",
  });
  const cloudPct = item.cloud_cover != null ? `${item.cloud_cover.toFixed(1)}%` : "—";
  const roleColor = role === "before" ? "var(--accent-amber)" : "var(--accent-blue)";

  return (
    <div className="ic-card">
      <div className="ic-card-header" style={{ borderLeftColor: roleColor }}>
        <span className="ic-role" style={{ color: roleColor }}>{role.toUpperCase()}</span>
        <span className="ic-collection">{item.collection}</span>
      </div>
      {item.thumbnail_url && (
        <img
          src={item.thumbnail_url}
          alt={`${role} scene thumbnail`}
          className="ic-thumb"
          loading="lazy"
        />
      )}
      <dl className="ic-meta">
        <dt>Date</dt><dd>{acqDate}</dd>
        <dt>Provider</dt><dd>{item.provider}</dd>
        <dt>Cloud cover</dt><dd>{cloudPct}</dd>
        <dt>Item ID</dt><dd className="ic-id" title={item.item_id}>{item.item_id.slice(-12)}</dd>
      </dl>
    </div>
  );
}

export function ImageryComparePanel({ items }: Props) {
  // Sort items by date so the compare selection works chronologically
  const sorted = [...items].sort(
    (a, b) => new Date(a.datetime).getTime() - new Date(b.datetime).getTime()
  );

  const [beforeIdx, setBeforeIdx] = useState(0);
  const [afterIdx, setAfterIdx] = useState(Math.max(sorted.length - 1, 0));

  if (!sorted.length) {
    return (
      <div className="panel ic-empty">
        <p className="text-muted">No imagery results yet. Search imagery in an AOI first.</p>
      </div>
    );
  }

  const before = sorted[beforeIdx];
  const after = sorted[afterIdx];

  const daysDiff = before && after
    ? Math.round(
        (new Date(after.datetime).getTime() - new Date(before.datetime).getTime()) /
        (1000 * 60 * 60 * 24)
      )
    : 0;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Imagery Compare</span>
        {daysDiff > 0 && (
          <span className="ic-gap-badge">{daysDiff}d apart</span>
        )}
      </div>

      {/* Selector row */}
      <div className="ic-selectors">
        <div className="ic-selector">
          <label className="label-sm" style={{ color: "var(--accent-amber)" }}>Before scene</label>
          <select
            className="input-sm"
            value={beforeIdx}
            onChange={e => setBeforeIdx(Number(e.target.value))}
          >
            {sorted.map((item, i) => (
              <option key={item.item_id} value={i} disabled={i === afterIdx}>
                {new Date(item.datetime).toLocaleDateString()} — {item.collection}
              </option>
            ))}
          </select>
        </div>
        <div className="ic-swap">
          <button
            className="btn btn-xs"
            title="Swap before/after"
            onClick={() => { const tmp = beforeIdx; setBeforeIdx(afterIdx); setAfterIdx(tmp); }}
          >⇄</button>
        </div>
        <div className="ic-selector">
          <label className="label-sm" style={{ color: "var(--accent-blue)" }}>After scene</label>
          <select
            className="input-sm"
            value={afterIdx}
            onChange={e => setAfterIdx(Number(e.target.value))}
          >
            {sorted.map((item, i) => (
              <option key={item.item_id} value={i} disabled={i === beforeIdx}>
                {new Date(item.datetime).toLocaleDateString()} — {item.collection}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Side-by-side cards */}
      <div className="ic-compare-row">
        {before && <ItemCard item={before} role="before" />}
        {after && <ItemCard item={after} role="after" />}
      </div>

      {/* Delta summary */}
      {before && after && before.cloud_cover != null && after.cloud_cover != null && (
        <div className="ic-delta">
          <span className="ic-delta-label">Cloud cover delta</span>
          <span
            className="ic-delta-value"
            style={{ color: after.cloud_cover > before.cloud_cover ? "var(--accent-red)" : "var(--accent-green)" }}
          >
            {after.cloud_cover > before.cloud_cover ? "+" : ""}
            {(after.cloud_cover - before.cloud_cover).toFixed(1)}%
          </span>
        </div>
      )}
    </div>
  );
}
