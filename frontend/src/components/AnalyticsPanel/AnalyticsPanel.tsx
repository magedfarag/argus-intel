import { useState } from "react";
import { useSubmitChangeJob, useReviewCandidate, useCandidates } from "../../hooks/useAnalytics";
import type { ChangeCandidate, ReviewDecision } from "../../api/types";

interface Props { aoiId: string | null; startTime: string; endTime: string }

export function AnalyticsPanel({ aoiId, startTime, endTime }: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const submitJob = useSubmitChangeJob();
  const { data: candidates = [] } = useCandidates(jobId);
  const reviewCandidate = useReviewCandidate();

  function handleSubmit() {
    if (!aoiId) return;
    submitJob.mutate({ aoiId, startDate: startTime.slice(0, 10), endDate: endTime.slice(0, 10) }, {
      onSuccess: job => setJobId(job.job_id),
    });
  }

  function handleReview(id: string, decision: ReviewDecision) {
    reviewCandidate.mutate({ id, decision });
  }

  const statusColor = (s: string) => s === "confirmed" ? "#16a34a" : s === "dismissed" ? "#dc2626" : "#d97706";

  return (
    <div className="panel" data-testid="analytics-panel">
      <h3 className="panel-title">Change Detection</h3>
      <button
        className="btn btn-primary btn-sm"
        onClick={handleSubmit}
        disabled={!aoiId || submitJob.isPending}
        data-testid="submit-change-job-btn"
      >
        {submitJob.isPending ? "Running…" : "Run Change Detection"}
      </button>
      {submitJob.isError && <p className="error">Failed: {String(submitJob.error)}</p>}
      {candidates.length > 0 && (
        <ul className="candidate-list">
          {candidates.map((c: ChangeCandidate) => (
            <li key={c.candidate_id} className="candidate-item">
              <div className="candidate-header">
                <span className="candidate-class">{c.change_class.replace(/_/g, " ")}</span>
                <span className="candidate-confidence">{Math.round(c.confidence * 100)}%</span>
              </div>
              <p className="candidate-rationale">{c.rationale}</p>
              {c.review_status === "pending" ? (
                <div className="review-actions">
                  <button className="btn btn-sm btn-success" onClick={() => handleReview(c.candidate_id, "confirmed")}>✓ Confirm</button>
                  <button className="btn btn-sm btn-danger" onClick={() => handleReview(c.candidate_id, "dismissed")}>✕ Dismiss</button>
                </div>
              ) : (
                <span style={{ color: statusColor(c.review_status) }}>{c.review_status}</span>
              )}
            </li>
          ))}
        </ul>
      )}
      {jobId && candidates.length === 0 && <p className="muted">No candidates found</p>}
    </div>
  );
}