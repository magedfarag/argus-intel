import { useState } from "react";
import { exportsApi } from "../../api/client";

interface Props {
  aoiId: string | null;
  startTime: string;
  endTime: string;
}

export function ExportPanel({ aoiId, startTime, endTime }: Props) {
  const [format, setFormat] = useState<"csv" | "geojson">("csv");
  const [status, setStatus] = useState<string>("");
  const [downloading, setDownloading] = useState(false);

  async function handleExport() {
    setDownloading(true);
    setStatus("Submitting…");
    try {
      const job = await exportsApi.create({
        ...(aoiId ? { aoi_id: aoiId } : {}),
        start_time: startTime,
        end_time: endTime,
        format,
      });
      // Poll for completion
      const poll = async () => {
        const j = await exportsApi.get(job.job_id);
        if (j.state === "completed") {
          setStatus(`Done — ${j.row_count ?? "?"} rows`);
          if (j.download_url) window.open(j.download_url, "_blank");
        } else if (j.state === "failed") {
          setStatus("Export failed");
        } else {
          setTimeout(poll, 1500);
        }
      };
      await poll();
    } catch (e) {
      setStatus(`Error: ${e}`);
    } finally { setDownloading(false); }
  }

  return (
    <div className="panel" data-testid="export-panel">
      <h3 className="panel-title">Export</h3>
      <div className="export-controls">
        <select className="input-sm" value={format} onChange={e => setFormat(e.target.value as "csv" | "geojson")}>
          <option value="csv">CSV</option>
          <option value="geojson">GeoJSON</option>
        </select>
        <button className="btn btn-primary btn-sm" onClick={handleExport} disabled={downloading} data-testid="export-btn">
          {downloading ? "Exporting…" : "Export"}
        </button>
      </div>
      {status && <p className="muted">{status}</p>}
    </div>
  );
}