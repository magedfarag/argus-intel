import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { UseInvestigationsResult } from '../../../hooks/useInvestigations';

// Mock the hook before importing the component
const mockUseInvestigations = vi.fn<() => UseInvestigationsResult>();
vi.mock('../../../hooks/useInvestigations', () => ({
  useInvestigations: () => mockUseInvestigations(),
}));

import { InvestigationsPanel } from '../InvestigationsPanel';

const defaultResult: UseInvestigationsResult = {
  investigations: [],
  absenceSignals: [],
  absenceAlerts: [],
  loading: false,
  error: null,
  createInvestigation: vi.fn(),
  addNote: vi.fn(),
  deleteInvestigation: vi.fn(),
  refreshInvestigations: vi.fn(),
  generateAndDownloadEvidencePack: vi.fn(),
  generateAndShowBriefing: vi.fn(),
};

beforeEach(() => {
  mockUseInvestigations.mockReturnValue(defaultResult);
});

describe('InvestigationsPanel smoke', () => {
  it('exports a React component function', () => {
    expect(InvestigationsPanel).toBeTypeOf('function');
  });

  it('renders nothing when visible=false', () => {
    const { container } = render(<InvestigationsPanel visible={false} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders without throwing when visible=true', () => {
    expect(() => render(<InvestigationsPanel visible={true} />)).not.toThrow();
  });

  it('shows loading state when loading=true', () => {
    mockUseInvestigations.mockReturnValue({ ...defaultResult, loading: true });
    render(<InvestigationsPanel visible={true} />);
    expect(screen.getByText(/loading investigations/i)).toBeTruthy();
  });

  it('shows "New" button when visible=true', () => {
    render(<InvestigationsPanel visible={true} />);
    expect(screen.getByText('+ New')).toBeTruthy();
  });

  it('shows error message when error is set', () => {
    mockUseInvestigations.mockReturnValue({ ...defaultResult, error: 'Network failure' });
    render(<InvestigationsPanel visible={true} />);
    expect(screen.getByText('Network failure')).toBeTruthy();
  });

  it('renders investigation list items', () => {
    mockUseInvestigations.mockReturnValue({
      ...defaultResult,
      investigations: [
        {
          id: 'inv-1',
          name: 'Op Trident',
          status: 'active',
          created_at: '2026-04-01T10:00:00Z',
          updated_at: '2026-04-01T10:00:00Z',
          tags: [],
          watchlist: [],
          notes: [],
          evidence_links: [],
          linked_event_ids: [],
        },
      ],
    });
    render(<InvestigationsPanel visible={true} />);
    expect(screen.getByText('Op Trident')).toBeTruthy();
    expect(screen.getByText('active')).toBeTruthy();
  });
});
