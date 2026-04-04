// React hook for Phase 5 investigation workflow state.
// Follows the same AbortController pattern as useOperationalLayers.ts.

import { useCallback, useEffect, useState } from 'react';
import {
  fetchInvestigations,
  createInvestigation as apiCreate,
  addInvestigationNote as apiAddNote,
  deleteInvestigation as apiDelete,
  fetchAbsenceSignals,
  fetchAbsenceAlerts,
  generateEvidencePack,
  downloadEvidencePack,
  generateBriefing,
  fetchBriefingText,
} from '../api/investigationsApi';
import type {
  Investigation,
  InvestigationCreateRequest,
  AbsenceSignal,
  AbsenceAlert,
} from '../types/investigations';

export interface UseInvestigationsResult {
  investigations: Investigation[];
  absenceSignals: AbsenceSignal[];
  absenceAlerts: AbsenceAlert[];
  loading: boolean;
  error: string | null;
  createInvestigation: (req: InvestigationCreateRequest) => Promise<Investigation | null>;
  addNote: (id: string, content: string, author?: string) => Promise<void>;
  deleteInvestigation: (id: string) => Promise<void>;
  refreshInvestigations: () => void;
  generateAndDownloadEvidencePack: (investigation_id: string) => Promise<void>;
  generateAndShowBriefing: (investigation_id: string, title: string) => Promise<string>;
}

export function useInvestigations(): UseInvestigationsResult {
  const [investigations, setInvestigations] = useState<Investigation[]>([]);
  const [absenceSignals, setAbsenceSignals] = useState<AbsenceSignal[]>([]);
  const [absenceAlerts, setAbsenceAlerts] = useState<AbsenceAlert[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    Promise.all([
      fetchInvestigations(undefined, controller.signal),
      fetchAbsenceSignals(undefined, controller.signal),
      fetchAbsenceAlerts(controller.signal),
    ])
      .then(([invs, signals, alerts]) => {
        setInvestigations(invs);
        setAbsenceSignals(signals);
        setAbsenceAlerts(alerts);
      })
      .catch((err: unknown) => {
        if ((err as { name?: string }).name !== 'AbortError') {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => setLoading(false));

    return () => controller.abort();
  }, [refreshKey]);

  const refreshInvestigations = useCallback(() => {
    setRefreshKey(k => k + 1);
  }, []);

  const createInvestigation = useCallback(
    async (req: InvestigationCreateRequest): Promise<Investigation | null> => {
      try {
        const created = await apiCreate(req);
        setRefreshKey(k => k + 1);
        return created;
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
        return null;
      }
    },
    [],
  );

  const addNote = useCallback(
    async (id: string, content: string, author?: string): Promise<void> => {
      try {
        await apiAddNote(id, content, author);
        setRefreshKey(k => k + 1);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [],
  );

  const deleteInvestigation = useCallback(async (id: string): Promise<void> => {
    try {
      await apiDelete(id);
      setRefreshKey(k => k + 1);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }, []);

  const generateAndDownloadEvidencePack = useCallback(
    async (investigation_id: string): Promise<void> => {
      try {
        const { pack_id } = await generateEvidencePack(investigation_id);
        const text = await downloadEvidencePack(pack_id, 'markdown');
        // Trigger browser download
        const blob = new Blob([text], { type: 'text/markdown' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `evidence-pack-${pack_id}.md`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : String(err));
      }
    },
    [],
  );

  const generateAndShowBriefing = useCallback(
    async (investigation_id: string, title: string): Promise<string> => {
      try {
        const { briefing_id } = await generateBriefing(investigation_id, title);
        return await fetchBriefingText(briefing_id);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
        return '';
      }
    },
    [],
  );

  return {
    investigations,
    absenceSignals,
    absenceAlerts,
    loading,
    error,
    createInvestigation,
    addNote,
    deleteInvestigation,
    refreshInvestigations,
    generateAndDownloadEvidencePack,
    generateAndShowBriefing,
  };
}
