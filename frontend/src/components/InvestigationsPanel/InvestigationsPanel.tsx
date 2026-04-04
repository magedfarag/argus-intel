// InvestigationsPanel — Phase 5 analyst investigation workflow UI.
// Follows the same .panel / .panel-title patterns as OperationalLayersPanel.tsx and DarkShipPanel.tsx.

import { useState } from 'react';
import { useInvestigations } from '../../hooks/useInvestigations';
import type {
  Investigation,
  InvestigationStatus,
  AbsenceSeverity,
  AbsenceSignalType,
} from '../../types/investigations';

interface InvestigationsPanelProps {
  visible: boolean;
}

const STATUS_COLOR: Record<InvestigationStatus, string> = {
  draft:    '#64748b',
  active:   '#22c55e',
  archived: '#eab308',
  closed:   '#dc2626',
};

const SEVERITY_COLOR: Record<AbsenceSeverity, string> = {
  low:      '#22c55e',
  medium:   '#eab308',
  high:     '#f97316',
  critical: '#dc2626',
};

const SIGNAL_LABEL: Record<AbsenceSignalType, string> = {
  ais_gap:           'AIS Gap',
  gps_denial:        'GPS Denial',
  camera_silence:    'Camera Silence',
  expected_missing:  'Expected Missing',
  comm_blackout:     'Comm Blackout',
  track_termination: 'Track Terminated',
};

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

export function InvestigationsPanel({ visible }: InvestigationsPanelProps) {
  const {
    investigations,
    absenceSignals,
    absenceAlerts,
    loading,
    error,
    createInvestigation,
    addNote,
    deleteInvestigation,
    generateAndDownloadEvidencePack,
    generateAndShowBriefing,
  } = useInvestigations();

  const [showCreateForm, setShowCreateForm] = useState(false);
  const [createName, setCreateName] = useState('');
  const [createDesc, setCreateDesc] = useState('');
  const [createTags, setCreateTags] = useState('');
  const [creating, setCreating] = useState(false);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [noteContent, setNoteContent] = useState('');
  const [noteAuthor, setNoteAuthor] = useState('');
  const [addingNote, setAddingNote] = useState(false);

  const [showAbsence, setShowAbsence] = useState(false);
  const [briefingText, setBriefingText] = useState<string | null>(null);
  const [briefingSubject, setBriefingSubject] = useState<string | null>(null);
  const [packLoading, setPackLoading] = useState<string | null>(null);
  const [briefingLoading, setBriefingLoading] = useState<string | null>(null);

  if (!visible) return null;

  const selectedInv: Investigation | undefined =
    selectedId ? investigations.find(i => i.id === selectedId) : undefined;

  async function handleCreate() {
    if (!createName.trim()) return;
    setCreating(true);
    await createInvestigation({
      name: createName.trim(),
      description: createDesc.trim() || undefined,
      tags: createTags ? createTags.split(',').map(t => t.trim()).filter(Boolean) : [],
    });
    setCreating(false);
    setShowCreateForm(false);
    setCreateName('');
    setCreateDesc('');
    setCreateTags('');
  }

  async function handleAddNote(invId: string) {
    if (!noteContent.trim()) return;
    setAddingNote(true);
    await addNote(invId, noteContent.trim(), noteAuthor.trim() || undefined);
    setAddingNote(false);
    setNoteContent('');
    setNoteAuthor('');
  }

  async function handleEvidencePack(invId: string) {
    setPackLoading(invId);
    await generateAndDownloadEvidencePack(invId);
    setPackLoading(null);
  }

  async function handleBriefing(inv: Investigation) {
    setBriefingLoading(inv.id);
    const text = await generateAndShowBriefing(inv.id, `Briefing: ${inv.name}`);
    setBriefingLoading(null);
    if (text) {
      setBriefingText(text);
      setBriefingSubject(inv.name);
    }
  }

  const activeAlerts = absenceAlerts.filter(
    a => a.severity === 'high' || a.severity === 'critical',
  );

  return (
    <div className="panel" data-testid="investigations-panel">
      {/* Header */}
      <div className="panel-header">
        <h3 className="panel-title">Investigations</h3>
        <button
          className="btn btn-xs btn-active"
          onClick={() => setShowCreateForm(v => !v)}
          title="New investigation"
        >
          + New
        </button>
      </div>

      {/* Error */}
      {error && (
        <p className="error" style={{ fontSize: '0.75rem', margin: '4px 0' }}>
          {error}
        </p>
      )}

      {/* Create form */}
      {showCreateForm && (
        <div
          style={{
            background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.1)',
            borderRadius: 4,
            padding: '8px',
            marginBottom: 8,
          }}
        >
          <input
            className="input-sm"
            placeholder="Name *"
            value={createName}
            onChange={e => setCreateName(e.target.value)}
            style={{ width: '100%', marginBottom: 4 }}
          />
          <input
            className="input-sm"
            placeholder="Description"
            value={createDesc}
            onChange={e => setCreateDesc(e.target.value)}
            style={{ width: '100%', marginBottom: 4 }}
          />
          <input
            className="input-sm"
            placeholder="Tags (comma-separated)"
            value={createTags}
            onChange={e => setCreateTags(e.target.value)}
            style={{ width: '100%', marginBottom: 6 }}
          />
          <div style={{ display: 'flex', gap: 6 }}>
            <button
              className="btn btn-xs btn-active"
              onClick={() => void handleCreate()}
              disabled={creating || !createName.trim()}
            >
              {creating ? 'Creating…' : 'Create'}
            </button>
            <button
              className="btn btn-xs"
              onClick={() => setShowCreateForm(false)}
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Loading */}
      {loading && <p className="muted">Loading investigations…</p>}

      {/* Investigation list */}
      {!loading && investigations.length === 0 && (
        <p className="muted">No investigations yet</p>
      )}

      <ul style={{ listStyle: 'none', margin: 0, padding: 0 }}>
        {investigations.map(inv => (
          <li
            key={inv.id}
            style={{
              borderBottom: '1px solid rgba(255,255,255,0.07)',
              padding: '6px 0',
            }}
          >
            {/* Row summary */}
            <div
              style={{ display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer' }}
              onClick={() => setSelectedId(selectedId === inv.id ? null : inv.id)}
            >
              <span
                style={{
                  display: 'inline-block',
                  background: STATUS_COLOR[inv.status],
                  color: '#000',
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  borderRadius: 3,
                  padding: '1px 5px',
                  textTransform: 'uppercase',
                }}
              >
                {inv.status}
              </span>
              <span style={{ fontWeight: 600, flex: 1, fontSize: '0.85rem' }}>{inv.name}</span>
            </div>
            <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.45)', marginTop: 2 }}>
              {formatDate(inv.created_at)} &nbsp;·&nbsp;
              {inv.evidence_links.length} evidence &nbsp;·&nbsp;
              {inv.watchlist.length} watchlist
              {inv.tags.length > 0 && (
                <> &nbsp;·&nbsp; {inv.tags.join(', ')}</>
              )}
            </div>

            {/* Actions row */}
            <div style={{ display: 'flex', gap: 4, marginTop: 4, flexWrap: 'wrap' }}>
              <button
                className="btn btn-xs"
                onClick={() => setSelectedId(selectedId === inv.id ? null : inv.id)}
              >
                {selectedId === inv.id ? 'Collapse' : 'Notes'}
              </button>
              <button
                className="btn btn-xs"
                onClick={() => void handleEvidencePack(inv.id)}
                disabled={packLoading === inv.id}
                title="Generate and download evidence pack"
              >
                {packLoading === inv.id ? '…' : 'Export Pack'}
              </button>
              <button
                className="btn btn-xs"
                onClick={() => void handleBriefing(inv)}
                disabled={briefingLoading === inv.id}
                title="Generate analyst briefing"
              >
                {briefingLoading === inv.id ? '…' : 'Briefing'}
              </button>
              <button
                className="btn btn-xs"
                style={{ color: '#dc2626' }}
                onClick={() => void deleteInvestigation(inv.id)}
                title="Delete investigation"
              >
                Delete
              </button>
            </div>

            {/* Expanded detail */}
            {selectedId === inv.id && selectedInv && (
              <div
                style={{
                  marginTop: 8,
                  paddingLeft: 8,
                  borderLeft: '2px solid rgba(255,255,255,0.1)',
                }}
              >
                {/* Meta */}
                {selectedInv.description && (
                  <p style={{ fontSize: '0.75rem', color: 'rgba(255,255,255,0.6)', margin: '0 0 6px' }}>
                    {selectedInv.description}
                  </p>
                )}
                <div style={{ fontSize: '0.7rem', color: 'rgba(255,255,255,0.4)', marginBottom: 6 }}>
                  {selectedInv.linked_event_ids.length} linked events
                </div>

                {/* Watchlist */}
                {selectedInv.watchlist.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#00e5ff', marginBottom: 3 }}>
                      WATCHLIST
                    </div>
                    {selectedInv.watchlist.map(w => (
                      <div
                        key={w.id}
                        style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.6)', marginBottom: 2 }}
                      >
                        <span style={{ color: '#fff' }}>{w.label ?? w.identifier}</span>
                        {' '}
                        <span style={{ color: 'rgba(255,255,255,0.4)' }}>({w.entry_type})</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* Notes */}
                <div style={{ marginBottom: 8 }}>
                  <div style={{ fontSize: '0.7rem', fontWeight: 700, color: '#00e5ff', marginBottom: 3 }}>
                    NOTES ({selectedInv.notes.length})
                  </div>
                  {selectedInv.notes.length === 0 && (
                    <p style={{ fontSize: '0.72rem', color: 'rgba(255,255,255,0.35)', margin: 0 }}>
                      No notes yet
                    </p>
                  )}
                  {selectedInv.notes.map(n => (
                    <div
                      key={n.id}
                      style={{
                        background: 'rgba(255,255,255,0.04)',
                        borderRadius: 3,
                        padding: '4px 6px',
                        marginBottom: 4,
                        fontSize: '0.75rem',
                      }}
                    >
                      <div>{n.content}</div>
                      <div style={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.35)', marginTop: 2 }}>
                        {n.author ? `${n.author} · ` : ''}{formatDate(n.created_at)}
                        {n.tags.length > 0 && ` · ${n.tags.join(', ')}`}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Add note form */}
                <div>
                  <textarea
                    className="input-sm"
                    placeholder="Add a note…"
                    value={noteContent}
                    onChange={e => setNoteContent(e.target.value)}
                    rows={2}
                    style={{ width: '100%', resize: 'vertical', marginBottom: 4 }}
                  />
                  <input
                    className="input-sm"
                    placeholder="Author (optional)"
                    value={noteAuthor}
                    onChange={e => setNoteAuthor(e.target.value)}
                    style={{ width: '100%', marginBottom: 4 }}
                  />
                  <button
                    className="btn btn-xs btn-active"
                    onClick={() => void handleAddNote(inv.id)}
                    disabled={addingNote || !noteContent.trim()}
                  >
                    {addingNote ? 'Saving…' : 'Add Note'}
                  </button>
                </div>
              </div>
            )}
          </li>
        ))}
      </ul>

      {/* Absence Signals sub-section */}
      <div style={{ marginTop: 12, borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: 8 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
          <button
            className={`btn btn-xs ${showAbsence ? 'btn-active' : ''}`}
            onClick={() => setShowAbsence(v => !v)}
          >
            Absence Signals
          </button>
          {activeAlerts.length > 0 && (
            <span
              style={{
                background: SEVERITY_COLOR.critical,
                color: '#000',
                borderRadius: 10,
                padding: '1px 7px',
                fontSize: '0.68rem',
                fontWeight: 700,
              }}
            >
              {activeAlerts.length} alert{activeAlerts.length !== 1 ? 's' : ''}
            </span>
          )}
        </div>

        {showAbsence && (
          <>
            {absenceSignals.length === 0 && (
              <p className="muted" style={{ fontSize: '0.75rem' }}>No absence signals</p>
            )}
            {absenceSignals.map(sig => (
              <div
                key={sig.signal_id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 6,
                  fontSize: '0.75rem',
                  padding: '3px 0',
                  borderBottom: '1px solid rgba(255,255,255,0.05)',
                }}
              >
                <span
                  style={{
                    background: 'rgba(0,229,255,0.12)',
                    color: '#00e5ff',
                    borderRadius: 3,
                    padding: '1px 5px',
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {SIGNAL_LABEL[sig.signal_type] ?? sig.signal_type}
                </span>
                <span style={{ flex: 1, color: 'rgba(255,255,255,0.75)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {sig.entity_id ?? '—'}
                </span>
                <span
                  style={{
                    background: SEVERITY_COLOR[sig.severity],
                    color: '#000',
                    borderRadius: 3,
                    padding: '1px 5px',
                    fontSize: '0.65rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                  }}
                >
                  {sig.severity}
                </span>
                <span style={{ color: 'rgba(255,255,255,0.4)', whiteSpace: 'nowrap' }}>
                  {Math.round(sig.confidence * 100)}%
                </span>
              </div>
            ))}
          </>
        )}
      </div>

      {/* Briefing modal */}
      {briefingText && (
        <div
          style={{
            position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.75)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
          onClick={() => { setBriefingText(null); setBriefingSubject(null); }}
        >
          <div
            style={{
              background: '#0c1a2e', border: '1px solid rgba(0,229,255,0.3)',
              borderRadius: 6, padding: 20, maxWidth: 600, width: '90%',
              maxHeight: '80vh', overflowY: 'auto',
            }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 12 }}>
              <strong style={{ fontSize: '0.9rem' }}>
                {briefingSubject ? `Briefing: ${briefingSubject}` : 'Analyst Briefing'}
              </strong>
              <button
                className="close-btn"
                onClick={() => { setBriefingText(null); setBriefingSubject(null); }}
              >
                ✕
              </button>
            </div>
            <pre
              style={{
                whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                fontSize: '0.8rem', color: 'rgba(255,255,255,0.8)', margin: 0,
              }}
            >
              {briefingText}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
}
