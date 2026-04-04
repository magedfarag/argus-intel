import { useQuery } from "@tanstack/react-query";
import { vesselsApi } from "../../api/client";
import type { VesselProfile } from "../../api/types";

const SANCTIONS_COLOR: Record<string, string> = {
  "OFAC-SDN": "#dc2626",
  "shadow-fleet": "#f97316",
  "watch-list": "#eab308",
  "UN-sanctioned": "#dc2626",
  "EU-sanctioned": "#f97316",
  clean: "#22c55e",
};

interface Props {
  mmsi: string;
  onClose: () => void;
}

export function VesselProfileModal({ mmsi, onClose }: Props) {
  const { data: vessel, isLoading } = useQuery({
    queryKey: ["vessel", mmsi],
    queryFn: () => vesselsApi.getByMmsi(mmsi),
    staleTime: 300_000,
  });

  return (
    <div className="modal-overlay" onClick={onClose} data-testid="vessel-modal">
      <div className="modal-card" onClick={e => e.stopPropagation()}>
        <button className="modal-close" onClick={onClose}>✕</button>
        {isLoading && <p className="muted">Loading vessel profile…</p>}
        {vessel && <VesselDetail vessel={vessel} />}
        {!isLoading && !vessel && (
          <p className="muted">No profile found for MMSI {mmsi}</p>
        )}
      </div>
    </div>
  );
}

function VesselDetail({ vessel }: { vessel: VesselProfile }) {
  const sColor = SANCTIONS_COLOR[vessel.sanctions_status] ?? "#64748b";
  return (
    <div className="vessel-detail">
      <div className="vessel-flag-row">
        <span className="vessel-flag-emoji">{vessel.flag_emoji}</span>
        <div>
          <h2 className="vessel-name">{vessel.name}</h2>
          <span className="vessel-type-tag">{vessel.vessel_type}</span>
        </div>
      </div>
      <span
        className="sanctions-status-badge"
        style={{ background: sColor }}
      >
        {vessel.sanctions_status}
      </span>
      {vessel.sanctions_detail && (
        <p className="sanctions-detail">{vessel.sanctions_detail}</p>
      )}
      <dl className="vessel-dl">
        <dt>IMO</dt><dd>{vessel.imo}</dd>
        <dt>MMSI</dt><dd>{vessel.mmsi}</dd>
        <dt>Flag</dt><dd>{vessel.flag}</dd>
        <dt>Owner</dt><dd>{vessel.owner}</dd>
        <dt>Operator</dt><dd>{vessel.operator}</dd>
        <dt>Built</dt><dd>{vessel.year_built}</dd>
        <dt>GT</dt><dd>{vessel.gross_tonnage.toLocaleString()}</dd>
        <dt>Last port</dt><dd>{vessel.last_known_port}</dd>
        <dt>Dark risk</dt>
        <dd>
          <span
            style={{ color: SANCTIONS_COLOR[vessel.dark_ship_risk] ?? (
              vessel.dark_ship_risk === "critical" ? "#dc2626" :
              vessel.dark_ship_risk === "high" ? "#f97316" : "#22c55e") }}
          >
            {vessel.dark_ship_risk.toUpperCase()}
          </span>
        </dd>
      </dl>
      {vessel.notes && <p className="vessel-notes muted-small">{vessel.notes}</p>}
    </div>
  );
}
