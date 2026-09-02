import { useState, useEffect, useCallback, useMemo } from 'react';
import { useLocation } from 'react-router-dom';
import { 
  fetchCases, 
  fetchMetrics, 
  reviewCase, 
  submitCase,
  investigateCase,
  batchInvestigateCases,
  batchSubmitCases,
  clearAllCases 
} from '../api/client';
import { Spinner } from '../components/Spinner';
import { DisputeTable } from '../components/DisputeTable';
import { DisputeHistoryTable } from '../components/DisputeHistoryTable';
import { DisputeDrawer } from '../components/DisputeDrawer';
import { CaseSimulatorModal } from '../components/CaseSimulatorModal';
import { IconTrash } from '../components/Icons';

const HISTORY_STATUSES = ['won', 'lost', 'submitted', 'rejected', 'closed'];

export function DisputesPage({ initialMode = 'queue' }) {
  const location = useLocation();
  const [metrics, setMetrics] = useState(null);
  const [cases, setCases] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCaseId, setSelectedCaseId] = useState(null);
  const [simulatorOpen, setSimulatorOpen] = useState(false);
  const [isClearing, setIsClearing] = useState(false);
  const [confirmReset, setConfirmReset] = useState(false);
  
  const viewMode = location.pathname === '/history' || initialMode === 'history' ? 'history' : 'queue';

  const load = useCallback(async (isInitial = false) => {
    if (isInitial) setLoading(true);
    try {
      const [m, c] = await Promise.all([
        fetchMetrics(),
        fetchCases({ per_page: 100 }),
      ]);
      setMetrics(m);
      setCases(c.cases || []);
    } catch (e) {
      console.error('Failed to load disputes data:', e);
    }
    if (isInitial) setLoading(false);
  }, []);

  useEffect(() => {
    load(true);

    const handleDataUpdated = () => {
      load(false);
    };

    window.addEventListener('raven:data-updated', handleDataUpdated);
    window.addEventListener('focus', handleDataUpdated);

    // Keep active cases and metrics synchronized in real-time
    const interval = setInterval(() => {
      load(false);
    }, 4000);

    return () => {
      window.removeEventListener('raven:data-updated', handleDataUpdated);
      window.removeEventListener('focus', handleDataUpdated);
      clearInterval(interval);
    };
  }, [load]);

  const handleCaseCreated = (caseId, result) => {
    load(false);
    if (result && result.auto_investigated) {
      setSelectedCaseId(caseId);
    }
  };

  const handleCasesCleared = () => {
    setCases([]);
    setSelectedCaseId(null);
    load(false);
  };

  const handleQuickAction = async (caseId, decision) => {
    const currentCase = cases.find((c) => c.case_id === caseId);

    // Guard: skip if already in a terminal state
    if (currentCase && ['submitted', 'rejected', 'won', 'lost', 'closed'].includes(currentCase.status)) {
      return;
    }

    // Optimistic update — removes from active queue immediately
    setCases((prev) =>
      prev.map((c) =>
        c.case_id === caseId
          ? { ...c, status: decision === 'approve' ? 'submitted' : 'rejected' }
          : c
      )
    );
    try {
      if (decision === 'approve') {
        if (currentCase && currentCase.status !== 'approved') {
          await reviewCase(caseId, 'approve', 'Approved & Submitted to Razorpay');
        }
        await submitCase(caseId);
      } else {
        await reviewCase(caseId, 'reject', 'Accepted dispute loss');
      }
      await load(false);
    } catch (e) {
      alert(`Action error: ${e.message}`);
      await load(false);
    }
  };

  const handleInvestigateCase = async (caseId) => {
    try {
      await investigateCase(caseId);
      await load(false);
    } catch (e) {
      alert(`Investigation failed: ${e.message}`);
    }
  };

  const handleBatchInvestigate = async () => {
    try {
      const res = await batchInvestigateCases();
      await load(false);
      return res;
    } catch (e) {
      alert(`Batch investigation failed: ${e.message}`);
    }
  };

  const handleBatchSubmit = async () => {
    try {
      const res = await batchSubmitCases();
      await load(false);
      return res;
    } catch (e) {
      alert(`Batch submit failed: ${e.message}`);
    }
  };

  const activeCases = useMemo(() => {
    return cases.filter(c => !HISTORY_STATUSES.includes(c.status));
  }, [cases]);

  /** Sandbox reset controls — rendered inside header actions */
  const sandboxControls = (
    <>
      {cases.length > 0 && !confirmReset && (
        <button 
          type="button" 
          className="btn btn-outline-danger btn-sm" 
          disabled={isClearing}
          onClick={() => setConfirmReset(true)}
          title="Reset sandbox"
        >
          <IconTrash size={12} />
          <span>Reset Sandbox</span>
        </button>
      )}

      {confirmReset && (
        <div className="queue-metric-chip" style={{ background: 'rgba(239, 68, 68, 0.08)', borderColor: 'rgba(239, 68, 68, 0.25)' }}>
          <span style={{ fontSize: '11px', color: 'var(--color-danger)', fontWeight: 500 }}>
            Purge all cases?
          </span>
          <button
            type="button"
            className="btn btn-danger btn-sm"
            disabled={isClearing}
            onClick={async () => {
              setIsClearing(true);
              try {
                await clearAllCases();
                handleCasesCleared();
                setConfirmReset(false);
              } catch (e) {
                console.error('Clear failed:', e);
              } finally {
                setIsClearing(false);
              }
            }}
            style={{ padding: '2px 8px', fontSize: '11px' }}
          >
            {isClearing ? 'Clearing...' : 'Confirm'}
          </button>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={isClearing}
            onClick={() => setConfirmReset(false)}
            style={{ padding: '2px 6px', fontSize: '11px' }}
          >
            Cancel
          </button>
        </div>
      )}
    </>
  );

  if (loading && !metrics && cases.length === 0) {
    return (
      <div className="page-center">
        <Spinner />
      </div>
    );
  }

  return (
    <div className="page">
      {/* VIEW 1: ACTIVE DISPUTES QUEUE */}
      {viewMode === 'queue' && (
        <DisputeTable 
          cases={activeCases}
          selectedCaseId={selectedCaseId}
          onSelectCase={(caseId) => setSelectedCaseId(caseId)}
          onQuickAction={handleQuickAction}
          onInvestigateCase={handleInvestigateCase}
          onBatchInvestigate={handleBatchInvestigate}
          onBatchSubmit={handleBatchSubmit}
          onOpenSimulator={() => setSimulatorOpen(true)}
          sandboxControls={sandboxControls}
        />
      )}

      {/* VIEW 2: HISTORICAL DISPUTE LEDGER */}
      {viewMode === 'history' && (
        <DisputeHistoryTable
          cases={cases}
          selectedCaseId={selectedCaseId}
          onSelectCase={(caseId) => setSelectedCaseId(caseId)}
          onOpenSimulator={() => setSimulatorOpen(true)}
          metrics={metrics}
        />
      )}

      {/* Slide-Over Quick Inspection Drawer (Active in both modes) */}
      <DisputeDrawer
        caseId={selectedCaseId}
        onClose={() => setSelectedCaseId(null)}
        onCaseUpdated={load}
      />

      {/* Case Simulator Modal */}
      <CaseSimulatorModal
        isOpen={simulatorOpen}
        onClose={() => setSimulatorOpen(false)}
        onCaseCreated={handleCaseCreated}
        onCasesCleared={handleCasesCleared}
      />
    </div>
  );
}
